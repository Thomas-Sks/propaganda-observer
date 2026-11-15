"use client";
/* Intro d'ouverture (~4,5 s, une fois par session, passable) : un œil s'ouvre ; dans l'iris, la Terre tourne et
   des flux d'information la parcourent. Puis on plonge dans l'iris et l'application apparaît. Purement décoratif. */
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import * as THREE from "three";
import { feature } from "topojson-client";
import land from "world-atlas/land-110m.json";
import "./intro.css";

const KEY = "observer:intro-seen";
const DURATION = 4600;

function dir(lat: number, lon: number, r = 1) {
  const la = THREE.MathUtils.degToRad(lat), lo = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo)).multiplyScalar(r);
}
const CITIES: [number, number][] = [
  [48.85, 2.35], [55.75, 37.62], [52.52, 13.4], [41.9, 12.5], [40.42, -3.7], [52.23, 21.01], [50.45, 30.52],
  [40.71, -74.0], [39.9, 116.4], [51.5, -0.12], [59.33, 18.07], [44.43, 26.1], [33.89, 35.5], [-23.55, -46.63],
];
const FLOWS: [number, number][] = [[1, 0], [1, 2], [1, 3], [1, 4], [1, 5], [6, 0], [7, 0], [8, 1], [9, 0], [1, 10], [1, 11], [12, 0], [0, 13], [2, 9]];

function earth(canvas: HTMLCanvasElement) {
  const size = canvas.clientWidth;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.setSize(size, size, false);
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(30, 1, 0.1, 10);
  cam.position.set(0, 0.35, 4.1); cam.lookAt(0, 0, 0);
  const g = new THREE.Group(); g.rotation.x = 0.35; scene.add(g);
  const add = (pts: number[], color: number, opacity: number) => {
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
    g.add(l); return l;
  };
  g.add(new THREE.Mesh(new THREE.SphereGeometry(0.995, 64, 64), new THREE.MeshBasicMaterial({ color: 0x03101c })));
  // graticule
  const gr: number[] = [];
  for (let lat = -60; lat <= 60; lat += 30) for (let lo = 0; lo < 360; lo += 5) { const a = dir(lat, lo), b = dir(lat, lo + 5); gr.push(a.x, a.y, a.z, b.x, b.y, b.z); }
  for (let lo = 0; lo < 360; lo += 30) for (let lat = -85; lat < 85; lat += 5) { const a = dir(lat, lo), b = dir(lat + 5, lo); gr.push(a.x, a.y, a.z, b.x, b.y, b.z); }
  add(gr, 0x22c5ee, 0.12);
  // côtes (Natural Earth 1:110m via world-atlas)
  const topo = land as unknown as Parameters<typeof feature>[0];
  const geo = feature(topo, topo.objects.land) as unknown as { features?: { geometry: { coordinates: number[][][][] } }[]; geometry?: { coordinates: number[][][][] } };
  const polys = (geo.features?.[0]?.geometry ?? geo.geometry)!.coordinates;
  const coast: number[] = [];
  for (const poly of polys) for (const ring of poly) for (let i = 0; i < ring.length - 1; i++) {
    const a = dir(ring[i][1], ring[i][0], 1.002), b = dir(ring[i + 1][1], ring[i + 1][0], 1.002); coast.push(a.x, a.y, a.z, b.x, b.y, b.z);
  }
  add(coast, 0x7fe6ff, 0.85);
  // atmosphère
  g.add(new THREE.Mesh(new THREE.SphereGeometry(1.12, 64, 64), new THREE.ShaderMaterial({
    transparent: true, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false,
    vertexShader: "varying vec3 n; varying vec3 v; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); n = normalize(normalMatrix*normal); v = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }",
    fragmentShader: "varying vec3 n; varying vec3 v; void main(){ float f = pow(1.0 - abs(dot(n, v)), 2.5); gl_FragColor = vec4(0.13,0.77,0.93,1.0)*f*0.8; }",
  })));
  // flux : arcs entre villes, avec une tête lumineuse
  const arcs = FLOWS.map(([a, b]) => {
    const A = dir(...CITIES[a], 1.003), B = dir(...CITIES[b], 1.003);
    const mid = A.clone().add(B).multiplyScalar(0.5).normalize().multiplyScalar(1 + A.distanceTo(B) * 0.35);
    return new THREE.QuadraticBezierCurve3(A, mid, B).getPoints(48);
  });
  const arcLines = arcs.map((pts) => {
    const geo = new THREE.BufferGeometry().setFromPoints(pts); geo.setDrawRange(0, 0);
    const l = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xff4d6a, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false }));
    g.add(l); return l;
  });
  const dots = new THREE.Points(new THREE.BufferGeometry().setFromPoints(CITIES.map((c) => dir(...c, 1.006))),
    new THREE.PointsMaterial({ color: 0xffd0d8, size: 0.035, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
  g.add(dots);
  const t0 = performance.now(); let raf = 0;
  const loop = () => {
    raf = requestAnimationFrame(loop);
    const t = (performance.now() - t0) / 1000;
    g.rotation.y = -THREE.MathUtils.degToRad(-60 + t * 18);  // termine Europe face à nous
    arcLines.forEach((l, i) => {
      const start = 0.9 + i * 0.12, u = Math.min(1, Math.max(0, (t - start) / 0.9));
      l.geometry.setDrawRange(0, Math.floor(u * 49));
    });
    renderer.render(scene, cam);
  };
  loop();
  return () => { cancelAnimationFrame(raf); renderer.dispose(); };
}

export default function Intro() {
  const path = usePathname();
  const [show, setShow] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let seen = true;
    try { seen = sessionStorage.getItem(KEY) === "1"; } catch {}
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (seen || reduced || path.startsWith("/login") || new URLSearchParams(location.search).has("nointro")) return;
    const id = setTimeout(() => setShow(true), 0);
    return () => clearTimeout(id);
  }, [path]);

  const end = () => { try { sessionStorage.setItem(KEY, "1"); } catch {} setShow(false); };

  useEffect(() => {
    if (!show || !canvas.current) return;
    const stop = earth(canvas.current);
    const a = setTimeout(() => setLeaving(true), DURATION - 800), b = setTimeout(() => { try { sessionStorage.setItem(KEY, "1"); } catch {} setShow(false); }, DURATION);
    return () => { stop(); clearTimeout(a); clearTimeout(b); };
  }, [show]);

  if (!show) return null;
  return (
    <div className={`intro ${leaving ? "intro-out" : ""}`} onClick={end}>
      <div className="intro-grid" />
      <div className="intro-boot">PARA-CELSUS // ESTABLISHING WATCH</div>
      <div className="intro-eye">
        <svg viewBox="0 0 600 300" className="intro-lids" aria-hidden>
          <defs>
            <clipPath id="intro-open"><path className="intro-open-path" d="M20 150 Q300 -40 580 150 Q300 340 20 150 Z" /></clipPath>
          </defs>
          <path className="intro-outline" d="M20 150 Q300 -40 580 150 Q300 340 20 150 Z" />
          <g clipPath="url(#intro-open)">
            <circle cx="300" cy="150" r="128" className="intro-iris-glow" />
          </g>
          <path className="intro-lash" d="M60 128 Q300 -30 540 128" />
        </svg>
        <div className="intro-iris">
          <canvas ref={canvas} />
          <svg viewBox="0 0 200 200" className="intro-ring"><circle cx="100" cy="100" r="96" /></svg>
          <svg viewBox="0 0 200 200" className="intro-ring2"><circle cx="100" cy="100" r="88" /></svg>
        </div>
      </div>
      <div className="intro-title">
        <div className="intro-kicker">PROGRAMME D&apos;OBSERVER</div>
        <div className="font-display">PARA-CELSUS</div>
        <span>Watching how information flows, and who pushes it</span>
      </div>
      <button className="intro-skip" onClick={end}>Skip ▸</button>
    </div>
  );
}
