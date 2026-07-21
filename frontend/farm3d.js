/* VertiBottle — 3D digital twin of a bottle-farm node (WebGL / Three.js).
 *
 * A real-time 3D rendering of one field node, driven by the same /readings
 * and /alerts data as the charts. It is a "digital twin": every moving part
 * reflects live telemetry, and acknowledging an alert plays the physical
 * corrective action while the reading actually recovers.
 *
 * Scene: solar array + battery, the recycled-bottle grow tower with plants,
 * the nutrient reservoir, pump and tubing, and the real sensor suite from
 * the SRS bill of materials (DS18B20, DHT22, DFRobot pH/TDS probes, HC-SR04
 * ultrasonic, BH1750) each surfaced in the HUD with its model number and a
 * live in-band/out-of-band readout.
 *
 * Exposes window.Farm = { mount, push, unmount } so app.js drives it exactly
 * like the previous 2D view. Depends on globals from app.js: t(), lang.
 */

import * as THREE from "/vendor/three.module.min.js";

const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const clamp01 = (x) => clamp(x, 0, 1);
const lerp = (a, b, k) => a + (b - a) * k;
const norm = (v, lo, hi) => clamp01((v - lo) / (hi - lo || 1));

// Real sensor suite (SRS 3.2 hardware table). Order matches the HUD cards.
const SENSORS = {
  ph:          { model: "DFRobot SEN0161-V2", kind: "Analog pH probe", unit: "" },
  ec:          { model: "DFRobot SEN0244",    kind: "TDS / EC probe",  unit: " µS/cm" },
  water_temp:  { model: "DS18B20",            kind: "1-Wire probe",    unit: " °C" },
  air_temp:    { model: "DHT22 (AM2302)",     kind: "Air temp",        unit: " °C" },
  humidity:    { model: "DHT22 (AM2302)",     kind: "Rel. humidity",   unit: " %" },
  water_level: { model: "HC-SR04",            kind: "Ultrasonic",      unit: " cm" },
  light:       { model: "BH1750",             kind: "Ambient light",   unit: " lux" },
};
const SENSOR_ORDER = ["ph", "ec", "water_temp", "air_temp", "humidity", "water_level", "light"];

const Farm = (() => {
  let root, hud, canvas;
  let renderer, scene, camera;
  let raf = null, ro = null;
  let site = null;
  let lastSeries = [], lastStates = {};

  // orbit state
  const target = new THREE.Vector3(-0.35, 1.4, 0.15);
  const orbit = { az: 0.6, pol: 1.18, rad: 8.7, autospin: true };

  // Ground-plan layout (x = right, z = toward front). The four subsystems
  // sit around the central tower so they spread across the frame instead of
  // lining up in depth.
  const POS = {
    tower: { x: 0, z: 0 },
    res:   { x: 1.85, z: 0.8 },
    solar: { x: -3.4, z: -1.5 },
    air:   { x: -1.55, z: 1.0 },
  };
  let dragging = false, px = 0, py = 0, idleFrames = 0;

  // live-driven scene handles, filled in build()
  const S = {};
  // particle emitters
  const emitters = [];
  let battery = 0.7, clock = 0;

  /* ---------------- materials ---------------- */

  const mat = {
    frame:   () => new THREE.MeshStandardMaterial({ color: 0x8a939c, roughness: 0.45, metalness: 0.75 }),
    deck:    () => new THREE.MeshStandardMaterial({ color: 0xced4da, roughness: 0.9, metalness: 0.05 }),
    bottle:  () => new THREE.MeshPhysicalMaterial({ color: 0xbfe6d4, roughness: 0.15, metalness: 0, transmission: 0.6, transparent: true, opacity: 0.55, thickness: 0.4 }),
    glass:   () => new THREE.MeshPhysicalMaterial({ color: 0xd6ebf5, roughness: 0.08, metalness: 0, transmission: 0.7, transparent: true, opacity: 0.35, thickness: 0.5 }),
    leaf:    () => new THREE.MeshStandardMaterial({ color: 0x3fa960, roughness: 0.6, metalness: 0 }),
    panel:   () => new THREE.MeshStandardMaterial({ color: 0x15315e, roughness: 0.25, metalness: 0.6, emissive: 0x0a1830, emissiveIntensity: 0.3 }),
    dark:    () => new THREE.MeshStandardMaterial({ color: 0x2b3038, roughness: 0.6, metalness: 0.4 }),
    white:   () => new THREE.MeshStandardMaterial({ color: 0xf2f4f6, roughness: 0.7, metalness: 0.1 }),
    accent:  () => new THREE.MeshStandardMaterial({ color: 0x2f6fa8, roughness: 0.5, metalness: 0.3 }),
  };

  /* ---------------- scene build ---------------- */

  function buildScene() {
    scene = new THREE.Scene();
    scene.background = null; // transparent; the container CSS provides a dark studio backdrop
    scene.fog = new THREE.Fog(0x121620, 16, 30);

    camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);

    // lights — dark-studio key + fill so glass, water and LEDs pop
    const hemi = new THREE.HemisphereLight(0xdCe8ff, 0x1a1e26, 1.0);
    scene.add(hemi);
    const fill = new THREE.DirectionalLight(0x7fa8ff, 0.5);
    fill.position.set(-5, 4, 6); scene.add(fill);
    const sun = new THREE.DirectionalLight(0xfff4e0, 2.4);
    sun.position.set(6.5, 9, 4.5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1; sun.shadow.camera.far = 30;
    sun.shadow.camera.left = -9; sun.shadow.camera.right = 9;
    sun.shadow.camera.top = 9; sun.shadow.camera.bottom = -9;
    sun.shadow.bias = -0.0004;
    scene.add(sun);
    S.sun = sun;

    // visible sun disc
    const sunDisc = new THREE.Mesh(
      new THREE.SphereGeometry(0.9, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0xffe08a })
    );
    sunDisc.position.copy(sun.position).multiplyScalar(1.05);
    scene.add(sunDisc);
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(1.6, 32, 32),
      new THREE.MeshBasicMaterial({ color: 0xffe9a8, transparent: true, opacity: 0.25 })
    );
    glow.position.copy(sunDisc.position);
    scene.add(glow);
    S.sunDisc = sunDisc; S.sunGlow = glow;

    // ground
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(16, 64),
      new THREE.MeshStandardMaterial({ color: 0x1c2129, roughness: 1, metalness: 0 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // concrete base pad (large, so it reads as the ground the rig stands on)
    const deck = new THREE.Mesh(new THREE.BoxGeometry(13, 0.25, 9),
      new THREE.MeshStandardMaterial({ color: 0x2c333d, roughness: 0.95, metalness: 0.05 }));
    deck.position.y = 0.125;
    deck.receiveShadow = true; deck.castShadow = true;
    scene.add(deck);

    buildSolar();
    buildTower();
    buildReservoir();
    buildSensors();
    buildControlBox();
    buildMist();

    updateCamera();
  }

  function post(x, y, z, h, r = 0.06, m = mat.frame()) {
    const p = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 12), m);
    p.position.set(x, y, z); p.castShadow = true;
    scene.add(p); return p;
  }

  function buildSolar() {
    const g = new THREE.Group();
    g.position.set(POS.solar.x, 0, POS.solar.z);
    // mast
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.1, 2.3, 16), mat.frame());
    mast.position.y = 1.15; mast.castShadow = true; g.add(mast);
    // tilted panel frame (2x2 cells), angled toward the sun (up and to the right)
    const arr = new THREE.Group();
    arr.position.set(0, 2.25, 0);
    arr.rotation.x = -Math.PI * 0.2; arr.rotation.y = 0.35;
    const backing = new THREE.Mesh(new THREE.BoxGeometry(1.86, 1.28, 0.07), mat.frame());
    backing.castShadow = true; arr.add(backing);
    S.solarCells = [];
    for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
      const cell = new THREE.Mesh(new THREE.BoxGeometry(0.84, 0.58, 0.05), mat.panel());
      cell.position.set(-0.46 + i * 0.92, -0.32 + j * 0.64, 0.055);
      arr.add(cell); S.solarCells.push(cell);
    }
    // specular glint bar that sweeps the panel when the sun is strong
    const glint = new THREE.Mesh(
      new THREE.PlaneGeometry(0.28, 1.24),
      new THREE.MeshBasicMaterial({ color: 0xbfe0ff, transparent: true, opacity: 0.0 })
    );
    glint.position.set(0, 0, 0.09);
    arr.add(glint); S.glint = glint;
    g.add(arr);
    S.solarArray = arr;

    // battery box
    const batt = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.44, 0.4), mat.dark());
    batt.position.set(0.5, 0.44, 0.8); batt.castShadow = true; g.add(batt);
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.44, 0.07, 0.02),
      new THREE.MeshStandardMaterial({ color: 0x2f9e5f, emissive: 0x2f9e5f, emissiveIntensity: 0.8 })
    );
    bar.position.set(0.5, 0.44, 1.0); g.add(bar);
    S.battBar = bar;
    scene.add(g);
    S.solarGroup = g;
  }

  function buildTower() {
    const g = new THREE.Group();
    g.position.set(POS.tower.x, 0, POS.tower.z);
    // recycled-bottle column: stacked translucent cylinders
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.46, 3.0, 32, 1, true), mat.bottle());
    col.position.y = 1.75; col.castShadow = true; g.add(col);
    // bottle ridges
    for (let k = 0; k < 5; k++) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.44, 0.03, 8, 32), mat.bottle());
      ring.rotation.x = Math.PI / 2; ring.position.y = 0.6 + k * 0.58; g.add(ring);
    }
    // planting cups + leaf clusters at 4 tiers, alternating sides
    S.plants = [];
    for (let k = 0; k < 4; k++) {
      const y = 0.95 + k * 0.55;
      const side = k % 2 === 0 ? 1 : -1;
      const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.09, 0.16, 12), mat.white());
      cup.position.set(side * 0.5, y, 0.1 * side); cup.castShadow = true; g.add(cup);
      const bunch = new THREE.Group();
      bunch.position.set(side * 0.66, y + 0.05, 0.1 * side);
      for (let l = 0; l < 6; l++) {
        const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.14, 10, 8), mat.leaf());
        leaf.scale.set(1.5, 0.5, 0.9);
        const a = (l / 6) * Math.PI * 2;
        leaf.position.set(Math.cos(a) * 0.16 * side, l * 0.02, Math.sin(a) * 0.12);
        leaf.rotation.z = side * 0.5; leaf.castShadow = true;
        bunch.add(leaf);
      }
      g.add(bunch); S.plants.push(bunch);
    }
    scene.add(g);
    S.tower = g;
  }

  function buildReservoir() {
    const g = new THREE.Group();
    g.position.set(POS.res.x, 0, POS.res.z);
    // glass tank in a metal cage (reads as a real IBC-style nutrient tote)
    const tank = new THREE.Mesh(new THREE.BoxGeometry(1.7, 1.0, 1.2), mat.glass());
    tank.position.y = 0.75; tank.castShadow = true; g.add(tank);
    const rim = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.07, 1.3), mat.frame());
    rim.position.y = 1.26; g.add(rim);
    const baseRim = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.09, 1.3), mat.frame());
    baseRim.position.y = 0.28; baseRim.castShadow = true; g.add(baseRim);
    for (const sx of [-0.85, 0.85]) for (const sz of [-0.6, 0.6]) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.07, 1.0, 0.07), mat.frame());
      p.position.set(sx, 0.77, sz); p.castShadow = true; g.add(p);
    }
    // water volume (scaled by level)
    const water = new THREE.Mesh(
      new THREE.BoxGeometry(1.58, 1.0, 1.08),
      new THREE.MeshPhysicalMaterial({ color: 0x2b7bbd, roughness: 0.1, metalness: 0, transmission: 0.2, transparent: true, opacity: 0.88 })
    );
    water.position.y = 0.55; g.add(water);
    S.water = water; S.waterGroup = g;

    // pump + tubing to tower
    const pump = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.3, 0.36), mat.accent());
    pump.position.set(-0.75, 0.42, 0.55); pump.castShadow = true; g.add(pump);
    S.pump = pump;
    // feed hose from the pump toward the tower (kept low and short, not a big arc)
    const hose = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.04, 10, 32, Math.PI * 0.62),
      new THREE.MeshStandardMaterial({ color: 0x8fa0ad, roughness: 0.5, metalness: 0.4 }));
    hose.position.set(-1.15, 0.5, 0.55); hose.rotation.z = -Math.PI * 0.28; g.add(hose);

    // shade panel that deploys over the tank when cooling/shading. Hidden
    // until needed, so it never floats in the scene as dead geometry.
    const shade = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.05, 1.5),
      new THREE.MeshStandardMaterial({ color: 0x6b7280, roughness: 0.85 }));
    shade.position.set(0, 1.42, 0); shade.castShadow = true; shade.visible = false; g.add(shade);
    S.shade = shade;
    scene.add(g);
  }

  function buildSensors() {
    S.markers = {};
    // probes into the reservoir (front edge of the tank, facing the camera)
    const resX = POS.res.x, resZ = POS.res.z, front = resZ + 0.42;
    probe(resX - 0.4, front, 0x111827, "ph");
    probe(resX - 0.05, front, 0xb45309, "ec");
    probe(resX + 0.3, front, 0xdc2626, "water_temp");

    // ultrasonic module on the tank rim (looks down at the water)
    const us = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.12, 0.16), mat.dark());
    us.position.set(resX + 0.5, 1.32, resZ - 0.35); scene.add(us);
    const eye = (dx) => { const e = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.06, 16), mat.frame()); e.position.set(resX + 0.5 + dx, 1.26, resZ - 0.35); scene.add(e); };
    eye(-0.06); eye(0.06);
    marker(resX + 0.5, 1.58, resZ - 0.35, "water_level");

    // DHT22 air sensor on a post in the air cluster
    const ax = POS.air.x, az = POS.air.z;
    post(ax, 0.9, az, 1.8);
    const dht = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.34, 0.1), mat.white());
    dht.position.set(ax, 1.75, az); dht.castShadow = true; scene.add(dht);
    const grille = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.28, 0.02), mat.dark());
    grille.position.set(ax, 1.75, az + 0.06); scene.add(grille);
    marker(ax, 2.05, az, "air_temp");
    marker(ax + 0.2, 1.95, az, "humidity");

    // BH1750 light sensor at the very top of the tower
    const tx = POS.tower.x, tz = POS.tower.z;
    const bh = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.06, 0.16), mat.dark());
    bh.position.set(tx, 3.35, tz); scene.add(bh);
    const dome = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.2 }));
    dome.position.set(tx, 3.38, tz); scene.add(dome);
    marker(tx, 3.62, tz, "light");
  }

  function probe(x, z, color, key) {
    const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 1.1, 12), new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.6 }));
    rod.position.set(x, 1.15, z); rod.castShadow = true; scene.add(rod);
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.14, 12), mat.dark());
    cap.position.set(x, 1.75, z); scene.add(cap);
    marker(x, 1.95, z, key);
  }

  // a small floating status pip above each subsystem (colour set from data)
  function marker(x, y, z, key) {
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(0.07, 16, 16),
      new THREE.MeshStandardMaterial({ color: 0x2f9e5f, emissive: 0x2f9e5f, emissiveIntensity: 0.6 })
    );
    m.position.set(x, y, z); m.visible = false; scene.add(m);
    S.markers[key] = m;
  }

  function buildControlBox() {
    const ax = POS.air.x, az = POS.air.z;
    const box = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.66, 0.28), mat.white());
    box.position.set(ax + 0.55, 0.55, az); box.castShadow = true; scene.add(box);
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 12), new THREE.MeshStandardMaterial({ color: 0x2f9e5f, emissive: 0x2f9e5f, emissiveIntensity: 1 }));
    led.position.set(ax + 0.73, 0.78, az + 0.15); scene.add(led);
    S.led = led;
  }

  /* ---------------- particle emitters ---------------- */

  function makeEmitter({ count, color, size, origin, spread, vel, gravity, life }) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    const seed = new Float32Array(count);
    for (let i = 0; i < count; i++) seed[i] = Math.random();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const points = new THREE.Points(geo, new THREE.PointsMaterial({
      color, size, transparent: true, opacity: 0.0, depthWrite: false,
      blending: THREE.AdditiveBlending, sizeAttenuation: true,
    }));
    points.frustumCulled = false;
    scene.add(points);
    const e = { points, geo, pos, seed, count, origin, spread, vel, gravity, life, on: false, strength: 0 };
    emitters.push(e);
    return e;
  }

  function buildMist() {
    const tx = POS.tower.x, tz = POS.tower.z, rx = POS.res.x, rz = POS.res.z;
    // humidity mist around the tower (always subtle, sprays hard when fixing)
    S.mist = makeEmitter({
      count: 260, color: 0xdff2ff, size: 0.07,
      origin: new THREE.Vector3(tx, 2.55, tz), spread: new THREE.Vector3(0.7, 0.7, 0.7),
      vel: new THREE.Vector3(0, -0.45, 0), gravity: -0.2, life: 2.2,
    });
    // doser droplets falling into the tank (pH / EC fixes)
    S.dose = makeEmitter({
      count: 60, color: 0x37c98a, size: 0.06,
      origin: new THREE.Vector3(rx, 1.5, rz), spread: new THREE.Vector3(0.12, 0.0, 0.12),
      vel: new THREE.Vector3(0, -1.4, 0), gravity: -1.0, life: 0.7,
    });
    // inflow stream into the tank (water-level fix)
    S.inflow = makeEmitter({
      count: 90, color: 0x6fc0ff, size: 0.05,
      origin: new THREE.Vector3(rx - 0.7, 1.4, rz), spread: new THREE.Vector3(0.06, 0.0, 0.2),
      vel: new THREE.Vector3(0.2, -1.6, 0), gravity: -1.2, life: 0.8,
    });
    // doser nozzle mesh above the tank
    const nozzle = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.02, 0.22, 12), mat.accent());
    nozzle.position.set(rx, 1.62, rz); scene.add(nozzle);

    // ventilation fan on a bracket beside the air sensor (spins when cooling)
    const fan = new THREE.Group();
    fan.position.set(POS.air.x - 0.5, 1.7, POS.air.z);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.08, 12), mat.dark());
    hub.rotation.x = Math.PI / 2; fan.add(hub);
    for (let i = 0; i < 4; i++) {
      const blade = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.1, 0.02), mat.frame());
      blade.position.set(Math.cos(i * Math.PI / 2) * 0.16, Math.sin(i * Math.PI / 2) * 0.16, 0);
      blade.rotation.z = i * Math.PI / 2 + 0.4; fan.add(blade);
    }
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.24, 0.02, 8, 24), mat.frame());
    fan.add(ring);
    scene.add(fan); S.fan = fan;
  }

  function stepEmitter(e, dt) {
    const target = e.on ? 1 : 0;
    e.strength = lerp(e.strength, target, 0.08);
    e.points.material.opacity = 0.75 * e.strength;
    if (e.strength < 0.01) return;
    for (let i = 0; i < e.count; i++) {
      // per-particle looping time from its seed
      const life = e.life;
      let ti = ((clock * (0.6 + e.seed[i] * 0.6)) % life);
      const f = ti / life;
      const j = i * 3;
      e.pos[j]     = e.origin.x + (e.seed[i] - 0.5) * e.spread.x + e.vel.x * ti;
      e.pos[j + 1] = e.origin.y + e.spread.y * (0.5 - f) + e.vel.y * ti + 0.5 * e.gravity * ti * ti;
      e.pos[j + 2] = e.origin.z + (((e.seed[i] * 7.13) % 1) - 0.5) * e.spread.z + e.vel.z * ti;
    }
    e.geo.attributes.position.needsUpdate = true;
  }

  /* ---------------- HUD ---------------- */

  function buildHud() {
    hud = document.createElement("div");
    hud.className = "twin-hud";
    hud.innerHTML = `
      <div class="twin-top">
        <span class="twin-title">${t("twin_title")}</span>
        <span class="twin-live"><span class="twin-dot"></span>${t("twin_live")}</span>
      </div>
      <div class="twin-power" id="twin-power"></div>
      <div class="twin-sensors" id="twin-sensors"></div>
      <div class="twin-caption" id="twin-caption"></div>
      <div class="twin-hint">${t("twin_hint")}</div>`;
    root.appendChild(hud);
  }

  function renderHud() {
    const by = {};
    lastSeries.forEach((s) => { by[s.parameter] = s; });

    // power / solar card
    const lightS = by.light;
    const gen = lightS && lightS.latest != null
      ? (norm(lightS.latest, lightS.band_min, lightS.band_max) * 6.0) : 0;
    document.getElementById("twin-power").innerHTML = `
      <div class="twin-card power">
        <div class="twin-k">${t("twin_solar")}</div>
        <div class="twin-v">${gen.toFixed(1)} W</div>
        <div class="twin-sub">${SENSORS_HW.solar}</div>
      </div>
      <div class="twin-card power">
        <div class="twin-k">${t("twin_batt")}</div>
        <div class="twin-v">${Math.round(battery * 100)} %</div>
        <div class="twin-batwrap"><div class="twin-bat" style="width:${Math.round(battery * 100)}%"></div></div>
      </div>
      <div class="twin-card power">
        <div class="twin-k">${t("twin_node")}</div>
        <div class="twin-v small">${SENSORS_HW.mcu}</div>
        <div class="twin-sub">${SENSORS_HW.link}</div>
      </div>`;

    // sensor cards
    document.getElementById("twin-sensors").innerHTML = SENSOR_ORDER.map((key) => {
      const s = by[key]; const meta = SENSORS[key];
      const st = lastStates[key];
      const cls = !st ? (s && s.in_band === false ? "out" : "ok")
        : st.kind === "watch" ? "watch" : st.kind === "fixing" ? "fixing" : "alarm";
      const val = s && s.latest != null ? s.latest + meta.unit : "—";
      return `<div class="twin-card sensor ${cls}">
        <div class="twin-srow"><span class="twin-dotc"></span><span class="twin-model">${meta.model}</span></div>
        <div class="twin-param">${t("param")[key]}</div>
        <div class="twin-v">${val}</div>
        <div class="twin-sub">${meta.kind}${s ? ` · ${t("target")} ${s.band_min}–${s.band_max}` : ""}</div>
      </div>`;
    }).join("");

    // caption: worst issue wins
    document.getElementById("twin-caption").innerHTML = caption(by);
  }

  const SENSORS_HW = {
    solar: "6 W PV + LiPo", mcu: "ESP32-WROOM-32", link: "Wi-Fi / SIM800L", };

  function caption(by) {
    const rank = { alarm: 0, fixing: 1, watch: 2 };
    const issues = Object.entries(lastStates).sort((a, b) => rank[a[1].kind] - rank[b[1].kind]);
    if (issues.length === 0) return `<span class="cap-ok">● ${t("twin_ok")}</span>`;
    const [param, st] = issues[0];
    const label = t("param")[param];
    const v = by[param] && by[param].latest != null ? ` (${by[param].latest})` : "";
    const more = issues.length > 1 ? ` <span class="muted">${t("farm_more").replace("{n}", issues.length - 1)}</span>` : "";
    if (st.kind === "fixing") {
      const action = t(`fix_${param}_${st.dir > 0 ? "high" : "low"}`);
      return `<span class="cap-fixing">▶ ${t("farm_fixing").replace("{param}", label).replace("{action}", action)}${v}</span>${more}`;
    }
    if (st.kind === "alarm") return `<span class="cap-alarm">■ ${t("farm_alarm").replace("{param}", label)}${v}</span>${more}`;
    return `<span class="cap-watch">▲ ${t("farm_watch").replace("{param}", label)}${v}</span>${more}`;
  }

  /* ---------------- data -> scene ---------------- */

  function paramStates(alerts) {
    const states = {};
    alerts.forEach((a) => {
      const dir = a.trigger_value > a.band_max ? 1 : -1;
      if (a.state === "acknowledged") states[a.parameter] = { kind: "fixing", dir };
      else if (a.state === "watch") states[a.parameter] = states[a.parameter] || { kind: "watch", dir };
      else if (a.state === "alert_raised" || a.state === "notification_sent") states[a.parameter] = { kind: "alarm", dir };
    });
    return states;
  }

  const MARK_COLOR = { ok: 0x2f9e5f, watch: 0xd99a1b, alarm: 0xd64545, fixing: 0x2f6fa8 };

  function applyData() {
    const by = {};
    lastSeries.forEach((s) => { by[s.parameter] = s; });

    // sun + solar from light
    const L = by.light;
    if (L && L.latest != null && S.sun) {
      const n = norm(L.latest, L.band_min, L.band_max);
      S.sun.intensity = lerp(1.1, 2.6, n);
      const dim = lerp(0.4, 1.0, n);
      S.sunDisc.material.color.setRGB(1, 0.88 * dim + 0.12, 0.5 * dim);
      S.sunGlow.material.opacity = lerp(0.1, 0.32, n);
      S.solarCells.forEach((c) => { c.material.emissiveIntensity = lerp(0.15, 0.55, n); });
      const tgt = clamp01(0.55 + 0.45 * n);
      battery = lerp(battery, tgt, 0.02);
      S.battBar.scale.x = clamp01(battery / 1);
      S.battBar.material.color.setHex(battery > 0.4 ? 0x2f9e5f : 0xd99a1b);
      S.battBar.material.emissive.setHex(battery > 0.4 ? 0x2f9e5f : 0xd99a1b);
    }

    // reservoir level + EC tint
    const WL = by.water_level, EC = by.ec, WT = by.water_temp;
    if (WL && WL.latest != null) {
      const h = clamp(norm(WL.latest, WL.band_min, WL.band_max), 0.12, 1);
      S.water.scale.y = h;
      S.water.position.y = 0.05 + (1.0 * h) / 2; // grow from tank floor
    }
    if (EC && EC.latest != null) {
      const n = norm(EC.latest, EC.band_min, EC.band_max);
      S.water.material.color.setRGB(lerp(0.18, 0.18, n), lerp(0.5, 0.62, n), lerp(0.75, 0.5, n));
    }
    if (WT && WT.latest != null) {
      const n = norm(WT.latest, WT.band_min, WT.band_max);
      // warmer water tints slightly toward teal-green; purely cosmetic
      S.water.material.emissive = S.water.material.emissive || new THREE.Color();
    }

    // plant health from worst state
    const worst = Object.values(lastStates).reduce((w, st) =>
      Math.min(w, st.kind === "alarm" ? 0 : st.kind === "fixing" ? 1 : st.kind === "watch" ? 2 : 3), 3);
    const healthy = worst >= 3;
    S.plants.forEach((b, idx) => {
      b.children.forEach((leaf) => {
        const c = healthy ? 0x3fa960 : worst === 0 ? 0x84a24e : worst === 1 ? 0x49a566 : 0x6fa554;
        leaf.material.color.setHex(c);
      });
      // droop when in alarm
      b.rotation.x = lerp(b.rotation.x, worst === 0 ? 0.5 : 0.0, 0.05);
    });
    S.led.material.color.setHex(worst === 0 ? 0xd64545 : worst <= 2 ? 0xd99a1b : 0x2f9e5f);
    S.led.material.emissive.setHex(worst === 0 ? 0xd64545 : worst <= 2 ? 0xd99a1b : 0x2f9e5f);

    // status markers
    Object.entries(S.markers).forEach(([key, m]) => {
      const st = lastStates[key];
      if (!st) { m.visible = false; return; }
      m.visible = true;
      const col = MARK_COLOR[st.kind] || MARK_COLOR.ok;
      m.material.color.setHex(col); m.material.emissive.setHex(col);
    });

    // corrective-action emitters + devices, keyed by which param is "fixing"
    const fixing = {};
    Object.entries(lastStates).forEach(([k, st]) => { if (st.kind === "fixing") fixing[k] = st; });

    S.mist.on = "humidity" in fixing || (by.humidity && by.humidity.in_band); // gentle mist tracks humidity, hard when fixing
    S.mist.life = "humidity" in fixing ? 1.4 : 2.4;
    S.dose.on = "ph" in fixing || "ec" in fixing;
    S.dose.points.material.color.setHex("ph" in fixing ? 0x7c9fd6 : 0x37c98a);
    S.inflow.on = ("water_level" in fixing) && fixing.water_level.dir < 0;
    S.fanOn = "air_temp" in fixing;
    S.pumpOn = ("water_level" in fixing) || Object.keys(fixing).length > 0;
    S.shadeOn = ("water_temp" in fixing && fixing.water_temp.dir > 0) || ("light" in fixing && fixing.light.dir > 0);
    S.anyFixing = Object.keys(fixing).length > 0;
  }

  /* ---------------- loop ---------------- */

  function updateCamera() {
    const x = target.x + orbit.rad * Math.sin(orbit.pol) * Math.cos(orbit.az);
    const y = target.y + orbit.rad * Math.cos(orbit.pol);
    const z = target.z + orbit.rad * Math.sin(orbit.pol) * Math.sin(orbit.az);
    camera.position.set(x, y, z);
    camera.lookAt(target);
  }

  function tick() {
    raf = requestAnimationFrame(tick);
    const dt = 1 / 60; clock += dt;

    if (orbit.autospin && !dragging) {
      idleFrames++;
      if (idleFrames > 180) orbit.az += 0.0016; // resume gentle spin after idle
    }
    updateCamera();

    // sun disc billboards toward camera glow already static; pulse markers
    Object.values(S.markers).forEach((m) => {
      if (m.visible) m.scale.setScalar(1 + Math.sin(clock * 4) * 0.18);
    });

    // devices
    if (S.fan) S.fan.children.forEach((c) => {}); // group rotation below
    if (S.fan) S.fan.rotation.z += (S.fanOn ? 0.5 : 0.02);
    if (S.pump) S.pump.material.emissiveIntensity = S.pumpOn ? (0.4 + Math.sin(clock * 8) * 0.3) : 0;
    if (S.pump && !S.pump.material.emissive) {}
    // shade deploys over the tank only while a cooling/shading fix runs
    if (S.shade) {
      S.shade.visible = !!S.shadeOn;
      if (S.shadeOn) S.shade.position.z = lerp(S.shade.position.z, 0, 0.1);
      else S.shade.position.z = 0.9;
    }
    // glint sweep on the solar panel
    if (S.glint) {
      const sweep = (clock * 0.35) % 2 - 1;
      S.glint.position.x = sweep * 1.1;
      const n = S.sun ? clamp01((S.sun.intensity - 1.1) / 1.5) : 0.5;
      S.glint.material.opacity = Math.max(0, (0.5 - Math.abs(sweep)) ) * 0.6 * n;
    }

    emitters.forEach((e) => stepEmitter(e, dt));
    renderer.render(scene, camera);
  }

  // pump needs an emissive channel; ensure material supports it
  function ensureEmissive() {
    if (S.pump) { S.pump.material.emissive = new THREE.Color(0x2f6fa8); S.pump.material.emissiveIntensity = 0; }
  }

  /* ---------------- interaction ---------------- */

  function bindPointer() {
    const el = renderer.domElement;
    el.addEventListener("pointerdown", (e) => { dragging = true; px = e.clientX; py = e.clientY; idleFrames = 0; el.setPointerCapture(e.pointerId); });
    el.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      orbit.az -= (e.clientX - px) * 0.006;
      orbit.pol = clamp(orbit.pol - (e.clientY - py) * 0.006, 0.35, 1.45);
      px = e.clientX; py = e.clientY; idleFrames = 0;
    });
    const up = () => { dragging = false; };
    el.addEventListener("pointerup", up); el.addEventListener("pointerleave", up);
    el.addEventListener("wheel", (e) => { e.preventDefault(); orbit.rad = clamp(orbit.rad + Math.sign(e.deltaY) * 0.5, 5.5, 13); }, { passive: false });
  }

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }

  /* ---------------- lifecycle ---------------- */

  function mount(containerEl, siteObj) {
    unmount();
    root = containerEl; site = siteObj;
    root.classList.add("twin-panel");
    root.innerHTML = "";

    canvas = document.createElement("canvas");
    canvas.className = "twin-canvas";
    root.appendChild(canvas);

    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch (err) {
      root.innerHTML = `<p class="empty">${t("twin_nowebgl")}</p>`;
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.18;

    buildScene();
    ensureEmissive();
    buildHud();
    bindPointer();
    resize();
    ro = new ResizeObserver(resize); ro.observe(canvas);
    tick();
  }

  function push(series, alerts) {
    if (!renderer) return;
    lastSeries = series || [];
    lastStates = paramStates(alerts || []);
    applyData();
    renderHud();
  }

  function unmount() {
    if (raf) cancelAnimationFrame(raf); raf = null;
    if (ro) { ro.disconnect(); ro = null; }
    emitters.length = 0;
    if (renderer) {
      renderer.dispose();
      renderer.forceContextLoss?.();
      renderer = null;
    }
    scene = null; camera = null;
    for (const k in S) delete S[k];
    if (root) { root.classList.remove("twin-panel"); root.innerHTML = ""; }
    root = null; hud = null; canvas = null;
    lastSeries = []; lastStates = {};
  }

  return { mount, push, unmount };
})();

window.Farm = Farm;
