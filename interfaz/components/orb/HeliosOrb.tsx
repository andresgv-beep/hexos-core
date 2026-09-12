"use client";

import { Component, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ACESFilmicToneMapping, AddEquation, CustomBlending, Group, MathUtils, NormalBlending, OneFactor, ShaderMaterial } from "three";
import { clampEnergy, phases, type OrbSignal } from "@/lib/helios/state";
import { createOrbGeometry, createOrbitGeometry, createMeshGlow } from "./geometry";
import { pointVertex, orbitPointVertex, pointFragment, cometVertex, lineVertex, lineFragment, surfaceVertex, surfaceFragment, coreFragment } from "./shaders";
import { orbTargetScale } from "@/lib/helios/motion";
import { Bloom } from "./Bloom";
import { meshGlowVertex, meshGlowFragment } from "./shaders";

export const MAX_FPS = 30;

export interface HeliosOrbProps {
  signal: OrbSignal;
  brightness?: number;
  motion?: boolean;
  sampleAmplitude?: (timeSeconds: number) => number;
}

function FrameTicker({ active }: { active: boolean }) {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    invalidate();
    if (!active) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const tick = () => {
      if (stopped) return;
      invalidate();
      timer = setTimeout(tick, 1000 / MAX_FPS);
    };
    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [active, invalidate]);
  return null;
}

function OrbScene({ signal, brightness = 1, motion = true, sampleAmplitude }: HeliosOrbProps) {
  const root = useRef<Group>(null);
  // three gives every ShaderMaterial its own copy of the `uniforms` object it is
  // constructed with, so driving them through one material's ref left the points,
  // comets and orbits frozen at their initial values — uViewportHeight stuck at 1
  // blew each sprite up into a screen-sized quad. Track every material instead.
  const materials = useRef(new Set<ShaderMaterial>());
  const bindMaterial = useCallback((instance: ShaderMaterial) => {
    materials.current.add(instance);
    return () => { materials.current.delete(instance); };
  }, []);
  const { invalidate, viewport } = useThree();
  const geometry = useMemo(() => createOrbGeometry(), []);
  const meshGlow = useMemo(() => createMeshGlow(geometry.lines), [geometry]);
  const orbits = useMemo(() => [createOrbitGeometry(0), createOrbitGeometry(1), createOrbitGeometry(2)], []);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uEnergy: { value: .16 }, uWarmth: { value: 0 },
    uBrightness: { value: 1 }, uViewportHeight: { value: 1 }, uAmplitude: { value: 0 },
    uFlowTime: { value: 0 },
    uViewportAspect: { value: 1 },
    uRestLight: { value: 1 },
  }), []);
  const elapsed = useRef(0);
  const expansion = useRef(.96);
  const signalTime = useRef(0);
  useEffect(() => { invalidate(); }, [signal, brightness, motion, invalidate]);
  useEffect(() => () => {
    geometry.points.dispose(); geometry.lines.dispose(); geometry.comets.dispose();
    meshGlow.dispose();
    orbits.forEach(orbit => { orbit.points.dispose(); orbit.line.dispose(); });
  }, [geometry, orbits, meshGlow]);
  useFrame((state, frameDelta) => {
    const values = uniforms;
    const dt = Math.min(frameDelta, .05), target = phases[signal.phase];
    if (motion) signalTime.current += dt;
    values.uFlowTime.value = signalTime.current;
    const amplitude = motion && sampleAmplitude ? clampEnergy(sampleAmplitude(signalTime.current)) : 0;
    const follow = motion ? 1 - Math.exp(-dt * (amplitude > values.uAmplitude.value ? 16 : 7)) : 1;
    values.uAmplitude.value = MathUtils.lerp(values.uAmplitude.value, amplitude, follow);
    const amount = motion ? 1 - Math.exp(-dt * 2.4) : 1;
    values.uEnergy.value = MathUtils.lerp(values.uEnergy.value, clampEnergy(signal.energy), amount);
    values.uWarmth.value = MathUtils.lerp(values.uWarmth.value, target.warmth, amount);
    values.uRestLight.value = MathUtils.lerp(values.uRestLight.value, signal.phase === "idle" ? 1 : 0, amount);
    values.uBrightness.value = MathUtils.clamp(brightness, .25, 2);
    values.uViewportHeight.value = state.size.height * state.gl.getPixelRatio();
    values.uViewportAspect.value = state.size.width / Math.max(state.size.height, 1);
    if (motion) elapsed.current += dt * (.65 + target.speed);
    values.uTime.value = elapsed.current;
    if (root.current) {
      const nextScale = orbTargetScale(signal.phase, signal.energy, values.uAmplitude.value, signalTime.current, motion);
      expansion.current = MathUtils.lerp(expansion.current, nextScale, motion ? 1 - Math.exp(-dt * 9) : 1);
      root.current.scale.setScalar(Math.min(viewport.width / 6.2, viewport.height / 5.6) * expansion.current);
      root.current.rotation.y = elapsed.current * .065 + (motion ? state.pointer.x * .035 : 0);
      root.current.rotation.x = .12 + (motion ? Math.sin(elapsed.current * .14) * .08 + state.pointer.y * .025 : 0);
    }
    for (const instance of materials.current) {
      for (const [name, uniform] of Object.entries(values)) instance.uniforms[name].value = uniform.value;
    }
  });
  // Plain one-to-one addition for colour *and* alpha, so `emit()`'s luminance
  // alpha accumulates alongside the light instead of being scaled by itself.
  const material = {
    uniforms, transparent: true, depthWrite: false, toneMapped: false,
    blending: CustomBlending, blendEquation: AddEquation,
    blendSrc: OneFactor, blendDst: OneFactor,
    blendSrcAlpha: OneFactor, blendDstAlpha: OneFactor,
  };
  return <group ref={root}>
    <mesh renderOrder={-1}>
      <sphereGeometry args={[1.79, 64, 48]} />
      <shaderMaterial ref={bindMaterial} uniforms={uniforms} transparent depthWrite={false} toneMapped={false} blending={NormalBlending} vertexShader={surfaceVertex} fragmentShader={coreFragment} />
    </mesh>
    <mesh><sphereGeometry args={[1.79, 160, 112]} /><shaderMaterial ref={bindMaterial} {...material} vertexShader={surfaceVertex} fragmentShader={surfaceFragment} /></mesh>
    <mesh geometry={geometry.points} frustumCulled={false}><shaderMaterial ref={bindMaterial} {...material} vertexShader={pointVertex} fragmentShader={pointFragment} /></mesh>
    <lineSegments geometry={geometry.lines}><shaderMaterial ref={bindMaterial} {...material} vertexShader={lineVertex} fragmentShader={lineFragment} /></lineSegments>
    <mesh geometry={meshGlow} frustumCulled={false}><shaderMaterial ref={bindMaterial} {...material} vertexShader={meshGlowVertex} fragmentShader={meshGlowFragment} /></mesh>
    <mesh geometry={geometry.comets} frustumCulled={false}><shaderMaterial ref={bindMaterial} {...material} vertexShader={cometVertex} fragmentShader={pointFragment} /></mesh>
    {orbits.map((orbit, i) => <group key={i} rotation={[[-.5, .65, 1.2][i], .2 + i * .35, [.3, -.5, .9][i]]}>
      <mesh geometry={orbit.points} frustumCulled={false}><shaderMaterial ref={bindMaterial} {...material} vertexShader={orbitPointVertex} fragmentShader={pointFragment} /></mesh>
      <lineLoop geometry={orbit.line}><shaderMaterial ref={bindMaterial} {...material} vertexShader={lineVertex} fragmentShader={lineFragment} /></lineLoop>
    </group>)}
  </group>;
}

function OrbFallback() {
  return <div className="orb-fallback" role="img" aria-label="Esfera de Helios en modo compatible"><div /><span>Modo compatible · WebGL no disponible</span></div>;
}

class OrbBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <OrbFallback /> : this.props.children; }
}

const emptySubscribe = () => () => {};
const clientReady = () => true;
const serverReady = () => false;
const visibilitySnapshot = () => document.visibilityState === "visible";
const motionSnapshot = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function subscribeVisibility(notify: () => void) {
  document.addEventListener("visibilitychange", notify);
  return () => document.removeEventListener("visibilitychange", notify);
}
function subscribeMotion(notify: () => void) {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change", notify);
  return () => media.removeEventListener("change", notify);
}

export function HeliosOrb(props: HeliosOrbProps) {
  const container = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(true);
  const ready = useSyncExternalStore(emptySubscribe, clientReady, serverReady);
  const visible = useSyncExternalStore(subscribeVisibility, visibilitySnapshot, clientReady);
  const reducedMotion = useSyncExternalStore(subscribeMotion, motionSnapshot, serverReady);
  useEffect(() => {
    if (!container.current) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: .01 });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const animate = props.motion !== false && !reducedMotion && visible && inView;
  return <div ref={container} className="orb-canvas" role="img" aria-label={`Esfera orgánica de Helios: ${phases[props.signal.phase].label}`}>
    {ready && <OrbBoundary><Canvas
      camera={{ position: [0, 0, 7.6], fov: 43 }}
      dpr={2}
      frameloop="demand"
      gl={{ alpha: true, antialias: false, powerPreference: "low-power", toneMapping: ACESFilmicToneMapping }}
      fallback={<OrbFallback />}
    >
      <FrameTicker active={animate} />
      <OrbScene {...props} motion={animate} />
      <Bloom />
    </Canvas></OrbBoundary>}
  </div>;
}
