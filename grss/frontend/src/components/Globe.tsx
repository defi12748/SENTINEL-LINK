"use client";

import { OrbitControls, Stars } from "@react-three/drei";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { GeoPoint } from "@/lib/api";

const R_EARTH_KM = 6371;

/** lat/lon (deg) → unit-sphere position matching three.js SphereGeometry UVs. */
export function toXYZ(lat: number, lon: number, r = 1): THREE.Vector3 {
  const la = (lat * Math.PI) / 180;
  const lo = (lon * Math.PI) / 180;
  return new THREE.Vector3(r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo));
}

/** Approximate sub-solar point for a Unix time (good to ~1°). */
function sunDirection(unix: number): THREE.Vector3 {
  const d = unix / 86400 - 10957.5; // days since J2000
  const g = ((357.529 + 0.98560028 * d) * Math.PI) / 180;
  const q = 280.459 + 0.98564736 * d;
  const L = ((q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * Math.PI) / 180;
  const e = ((23.439 - 0.00000036 * d) * Math.PI) / 180;
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
  const gmst = ((280.46061837 + 360.98564736629 * d) % 360) * (Math.PI / 180);
  const lon = ((ra - gmst) * 180) / Math.PI;
  return toXYZ((dec * 180) / Math.PI, ((lon + 540) % 360) - 180).normalize();
}

const earthVertex = /* glsl */ `
  varying vec2 vUv; varying vec3 vN;
  void main() { vUv = uv; vN = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const earthFragment = /* glsl */ `
  uniform sampler2D dayMap; uniform sampler2D nightMap; uniform vec3 sunDir;
  varying vec2 vUv; varying vec3 vN;
  void main() {
    float k = dot(normalize(vN), normalize(sunDir));
    float dayMix = smoothstep(-0.12, 0.22, k);
    vec3 day = texture2D(dayMap, vUv).rgb * (0.30 + 0.85 * max(k, 0.0));
    vec3 night = texture2D(nightMap, vUv).rgb * vec3(1.25, 1.05, 0.85);
    gl_FragColor = vec4(mix(night, day, dayMix), 1.0);
  }`;
const atmoVertex = /* glsl */ `
  varying vec3 vN; varying vec3 vView;
  void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`;
const atmoFragment = /* glsl */ `
  varying vec3 vN; varying vec3 vView;
  void main() { float f = pow(1.0 - abs(dot(vN, vView)), 3.2);
    gl_FragColor = vec4(0.32, 0.55, 1.0, 1.0) * f * 1.35; }`;

function Earth({ unix }: { unix: number }) {
  const [day, night] = useLoader(THREE.TextureLoader, ["/textures/earth_day.jpg", "/textures/earth_night.jpg"]);
  const uniforms = useMemo(() => {
    day.colorSpace = THREE.SRGBColorSpace;
    night.colorSpace = THREE.SRGBColorSpace;
    return { dayMap: { value: day }, nightMap: { value: night }, sunDir: { value: sunDirection(unix) } };
  }, [day, night, unix]);
  return (
    <group>
      <mesh>
        <sphereGeometry args={[1, 128, 128]} />
        <shaderMaterial uniforms={uniforms} vertexShader={earthVertex} fragmentShader={earthFragment} />
      </mesh>
      <mesh scale={1.035}>
        <sphereGeometry args={[1, 64, 64]} />
        <shaderMaterial vertexShader={atmoVertex} fragmentShader={atmoFragment} side={THREE.BackSide}
          blending={THREE.AdditiveBlending} transparent depthWrite={false} />
      </mesh>
    </group>
  );
}

function Polyline({ points, color, opacity = 1, dashed = false }:
  { points: THREE.Vector3[]; color: string; opacity?: number; dashed?: boolean }) {
  const line = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints(points);
    const m = dashed
      ? new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 0.012, gapSize: 0.01 })
      : new THREE.LineBasicMaterial({ color, transparent: true, opacity });
    const l = new THREE.Line(g, m);
    if (dashed) l.computeLineDistances();
    return l;
  }, [points, color, opacity, dashed]);
  return <primitive object={line} />;
}

function Pass({ orbit, pass, station, playhead, alert }: {
  orbit: GeoPoint[]; pass: GeoPoint[]; station: { lat: number; lon: number }; playhead: number; alert: boolean;
}) {
  const sat = useRef<THREE.Mesh>(null);
  const beam = useRef<THREE.Line>(null);
  const ring = useRef<THREE.Mesh>(null);
  const stationPos = useMemo(() => toXYZ(station.lat, station.lon, 1.002), [station]);
  const orbitPts = useMemo(() => orbit.map(p => toXYZ(p.lat, p.lon, 1 + p.alt_km / R_EARTH_KM)), [orbit]);
  const passPts = useMemo(() => pass.map(p => toXYZ(p.lat, p.lon, 1 + p.alt_km / R_EARTH_KM)), [pass]);
  const groundPts = useMemo(() => pass.map(p => toXYZ(p.lat, p.lon, 1.003)), [pass]);
  const beamGeom = useMemo(() => new THREE.BufferGeometry().setFromPoints([stationPos, stationPos.clone()]), [stationPos]);
  const beamMat = useMemo(() => new THREE.LineBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.9 }), []);
  const beamLine = useMemo(() => new THREE.Line(beamGeom, beamMat), [beamGeom, beamMat]);

  useFrame(({ clock }) => {
    if (!passPts.length) return;
    const f = Math.min(Math.max(playhead, 0), 1) * (passPts.length - 1);
    const i = Math.floor(f);
    const pos = passPts[i].clone().lerp(passPts[Math.min(i + 1, passPts.length - 1)], f - i);
    sat.current?.position.copy(pos);
    const attr = beamGeom.getAttribute("position") as THREE.BufferAttribute;
    attr.setXYZ(1, pos.x, pos.y, pos.z);
    attr.needsUpdate = true;
    beamMat.color.set(alert ? "#f64137" : "#8fb8ff");
    beamMat.opacity = 0.55 + 0.35 * Math.sin(clock.elapsedTime * 6);
    if (ring.current) {
      const s = 1 + ((clock.elapsedTime * 0.6) % 1) * 2.5;
      ring.current.scale.setScalar(s);
      (ring.current.material as THREE.MeshBasicMaterial).opacity = 1 - ((clock.elapsedTime * 0.6) % 1);
    }
  });

  const normal = stationPos.clone().normalize();
  const ringQuat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
  return (
    <group>
      {orbitPts.length > 1 && <Polyline points={orbitPts} color="#ffffff" opacity={0.28} />}
      {passPts.length > 1 && <Polyline points={passPts} color="#f64137" opacity={0.95} />}
      {groundPts.length > 1 && <Polyline points={groundPts} color="#ffffff" opacity={0.5} dashed />}
      <primitive object={beamLine} ref={beam} />
      <mesh ref={sat}>
        <sphereGeometry args={[0.012, 16, 16]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
      <mesh position={stationPos}>
        <sphereGeometry args={[0.008, 16, 16]} />
        <meshBasicMaterial color="#f64137" />
      </mesh>
      <mesh ref={ring} position={stationPos} quaternion={ringQuat}>
        <ringGeometry args={[0.012, 0.015, 48]} />
        <meshBasicMaterial color="#f64137" transparent side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function CameraRig({ target, shift: push = true }: { target: THREE.Vector3; shift?: boolean }) {
  const { size } = useThree();
  useFrame(({ camera }) => {
    const desired = target.clone().normalize().multiplyScalar(2.65);
    desired.y += 0.35;
    camera.position.lerp(desired, 0.02);
    camera.lookAt(0, 0, 0);
    // Wide screens: push the globe right so the station isn't under the headline.
    const pc = camera as THREE.PerspectiveCamera;
    const shift = push && size.width > 900 ? -size.width * 0.2 : 0;
    if (!pc.view || pc.view.offsetX !== shift || pc.view.fullWidth !== size.width) {
      pc.setViewOffset(size.width, size.height, shift, 0, size.width, size.height);
    }
  });
  return null;
}

function Markers({ points }: { points: { lat: number; lon: number }[] }) {
  return (
    <group>
      {points.map((p, i) => (
        <mesh key={i} position={toXYZ(p.lat, p.lon, 1.004)}>
          <sphereGeometry args={[0.009, 12, 12]} />
          <meshBasicMaterial color="#ffffff" />
        </mesh>
      ))}
    </group>
  );
}

export default function Globe({ orbit = [], pass = [], station, playhead = 0, alert = false, unix, follow = true, markers = [], shift = true }: {
  orbit?: GeoPoint[]; pass?: GeoPoint[]; station?: { lat: number; lon: number }; playhead?: number;
  alert?: boolean; unix: number; follow?: boolean; markers?: { lat: number; lon: number }[]; shift?: boolean;
}) {
  const target = useMemo(() => (station ? toXYZ(station.lat, station.lon) : new THREE.Vector3(1, 0.3, 0)), [station]);
  return (
    <Canvas camera={{ position: [0, 0.6, 2.8], fov: 38 }} dpr={[1, 2]} gl={{ antialias: true }}
      style={{ position: "absolute", inset: 0 }}>
      <color attach="background" args={["#000000"]} />
      <Stars radius={60} depth={40} count={6000} factor={3} fade speed={0.4} />
      <Earth unix={unix} />
      {station && <Pass orbit={orbit} pass={pass} station={station} playhead={playhead} alert={alert} />}
      {markers.length > 0 && <Markers points={markers} />}
      {follow && <CameraRig target={target} shift={shift} />}
      <OrbitControls enablePan={false} enableZoom={false} rotateSpeed={0.5} />
    </Canvas>
  );
}
