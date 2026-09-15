"use client";

import { useMemo, useRef, type RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { AddEquation, Color, CustomBlending, MathUtils, Matrix4, OneFactor, Vector3,
         type InstancedBufferAttribute, type Mesh, type ShaderMaterial } from "three";

export interface LabNote { id: string; title: string }

export interface ConstellationTuning {
  orbitRadius: number; orbitSpeed: number; sizePx: number;
  hue: number; graceMs: number; life: number; tilt: number; bubblePx: number;
}

// Spread rather than written inline: the React lint plugin does not know
// react-three-fiber's material props, exactly as HeliosOrb does it.
const BLEND = {
  transparent: true, depthWrite: false, toneMapped: false,
  blending: CustomBlending, blendEquation: AddEquation,
  blendSrc: OneFactor, blendDst: OneFactor,
  blendSrcAlpha: OneFactor, blendDstAlpha: OneFactor,
};

const noteVertex = /* glsl */ `
  uniform float uViewportHeight;
  uniform float uSizePx;
  varying vec2 vUv;
  void main() {
    vec4 mv = modelViewMatrix * vec4(0., 0., 0., 1.);
    float pixelsPerUnit = uViewportHeight * .5 * projectionMatrix[1][1] / -mv.z;
    mv.xy += position.xy * uSizePx / pixelsPerUnit;
    vUv = position.xy;
    gl_Position = projectionMatrix * mv;
  }
`;

// Same shape and alpha convention as the orb's own lights: a tight core inside a
// soft halo, with alpha tracking luminance so the transparent canvas composites
// it correctly instead of stamping an opaque patch over the page.
const noteFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uGlow;
  varying vec2 vUv;
  void main() {
    float r = length(vUv);
    float core = exp(-.5 * dot(vUv, vUv) / (.055 * .055));
    float halo = exp(-.5 * dot(vUv, vUv) / (.17 * .17)) * .35;
    float edge = 1. - smoothstep(.34, .5, r);
    vec3 c = (uColor * halo * 2. + mix(uColor, vec3(1.), .55) * core * 2.2) * uGlow * edge;
    gl_FragColor = vec4(c, max(max(c.r, c.g), c.b));
  }
`;

/** The orb's own surface wave, in JS, so a note leaves from exactly where its
 *  star is drawn. Mirrors `deform()` in the orb's shared shader chunk. */
function ride(p: Vector3, time: number, energy: number) {
  const length = p.length() || 1;
  const nx = p.x / length, ny = p.y / length, nz = p.z / length;
  const wave = Math.sin(nx * 5 + time * .65) * Math.sin(ny * 4 - time * .48)
             + .5 * Math.sin(nz * 7 + nx * 3 + time * .38);
  return p.multiplyScalar(1 + wave * (.012 + energy * .016));
}

/** The orb's bright stars are its first 800 instances. Notes borrow one each,
 *  spread apart so they never emerge from the same corner. */
const ANCHOR_STARS = 800;

export function NoteConstellation({ notes, pointer, tuning, markers }: {
  notes: LabNote[];
  /** Pointer distance from the orb's centre, in units of the sphere's on-screen radius. */
  pointer: RefObject<{ distance: number; x: number; y: number }>;
  tuning: RefObject<ConstellationTuning>;
  /** One positioned wrapper per note holding the bubble and the title. */
  markers: RefObject<(HTMLDivElement | null)[]>;
}) {
  const meshes = useRef<(Mesh | null)[]>([]);
  // three clones the `uniforms` object each material is built with, so writing to
  // the template never reaches the GPU — the same trap that once turned the orb's
  // stars into screen-sized quads. Hold the real material instances.
  const shaders = useRef<(ShaderMaterial | null)[]>([]);
  const stars = useRef<Mesh | null>(null);
  const open = useRef(0);
  const spin = useRef(0);
  /** Screen distance to the closest note, from the previous frame. One frame of
   *  lag is invisible and avoids a circular dependency with the orbit angle. */
  const reach = useRef(Infinity);
  const armedAt = useRef(0);
  /** Always advances, even when the orbit is held still for you. */
  const clock = useRef(0);
  /** The orb's own clock rule, so a borrowed star's wave stays in step. */
  const orbTime = useRef(0);
  const { size } = useThree();

  const templates = useMemo(() => notes.map(() => ({
    uniforms: { uViewportHeight: { value: 1 }, uSizePx: { value: 26 }, uColor: { value: new Color() }, uGlow: { value: 0 } },
  })), [notes]);

  // Deterministic, well separated: note n takes the star at the nth step of the
  // golden ratio around the anchor range.
  const starIndex = useMemo(
    () => notes.map((_, i) => Math.floor(((i * .61803398875) % 1) * ANCHOR_STARS)),
    [notes]);

  useFrame((state, frameDelta) => {
    const dt = Math.min(frameDelta, .05);
    clock.current += dt;
    orbTime.current += dt * (.65 + .14);
    const t = tuning.current, p = pointer.current;
    if (!t || !p) return;

    // Find the orb's star field once: the instanced mesh carrying per-star centres.
    if (!stars.current) {
      state.scene.traverse(object => {
        const mesh = object as Mesh;
        const attribute = mesh.geometry?.getAttribute?.("aCenter");
        if (attribute && attribute.count >= ANCHOR_STARS && !stars.current) stars.current = mesh;
      });
    }
    const field = stars.current;
    if (!field) return;

    // Opening is asked for on the core itself, never anywhere else on screen.
    // Staying open is granted over the whole constellation, so that reaching for
    // a note — which necessarily leaves the sphere — cannot dismiss it.
    const ring = t.orbitRadius / 1.8;
    const onCore = p.distance < 1;
    const onField = p.distance < ring + .5;
    const armed = onCore || (open.current > .05 && onField);
    if (armed) armedAt.current = performance.now();
    const wantOpen = armed || performance.now() - armedAt.current < t.graceMs ? 1 : 0;
    open.current = MathUtils.lerp(open.current, wantOpen, 1 - Math.exp(-dt * 6));

    // They notice you when you reach for one of *them*. Measuring closeness to
    // the orb's centre instead had it backwards: the ring sped up as you moved
    // out towards a note and froze when you sat in the middle touching nothing.
    const grab = MathUtils.clamp(1 - reach.current / 170, 0, 1);
    spin.current += dt * t.orbitSpeed * (1 - grab * .95);

    // Everything below works in world space, read from the orb's own matrix, so
    // its rotation, breathing and viewport scaling never have to be replicated.
    const world = field.matrixWorld as Matrix4;
    const centre = new Vector3().setFromMatrixPosition(world);
    const orbScale = new Vector3().setFromMatrixScale(world).x;
    const centres = field.geometry.getAttribute("aCenter") as InstancedBufferAttribute;

    const gold = new Color().setHSL(t.hue / 360, .85, .62);
    let nearest = -1, nearestD = Infinity;
    const projected: { x: number; y: number }[] = [];
    const opened: number[] = [];

    notes.forEach((_, i) => {
      const mesh = meshes.current[i];
      if (!mesh) return;
      const index = starIndex[i];
      const home = ride(new Vector3(centres.getX(index), centres.getY(index), centres.getZ(index)),
        orbTime.current, .16).applyMatrix4(world);

      const phase = i * 2.39996;
      const bob = Math.sin(clock.current * .9 + phase) * .07 * t.life;
      const sway = Math.cos(clock.current * .62 + phase * 1.7) * .06 * t.life;
      const radius = (t.orbitRadius + bob) * orbScale;
      const angle = spin.current + i / notes.length * Math.PI * 2 + sway / Math.max(t.orbitRadius, .001);
      const ring = new Vector3(
        centre.x + Math.cos(angle) * radius,
        centre.y + Math.sin(angle) * radius * t.tilt,
        centre.z,
      );

      const eased = open.current * open.current * (3 - 2 * open.current);
      mesh.position.lerpVectors(home, ring, eased);

      const ndc = mesh.position.clone().project(state.camera);
      const sx = (ndc.x * .5 + .5) * size.width;
      const sy = (-ndc.y * .5 + .5) * size.height;
      projected.push({ x: sx, y: sy });
      opened.push(eased);
      const d = Math.hypot(sx - p.x, sy - p.y);
      if (eased > .25 && d < nearestD) { nearestD = d; nearest = i; }

      const shader = shaders.current[i];
      if (shader) {
        const u = shader.uniforms;
        u.uViewportHeight.value = size.height * state.gl.getPixelRatio();
        u.uSizePx.value = t.sizePx;
        // A hand-off, not an overlay. At rest the star already there does the
        // work; once open the bubble does. The point only flares in between, so
        // it never sits as a blown highlight in the middle of the document.
        const twinkle = 1 + t.life * .26 * Math.sin(clock.current * 2.1 + phase * 3.1);
        u.uGlow.value = Math.sin(eased * Math.PI) * 1.45 * twinkle;
        (u.uColor.value as Color).copy(gold);
      }
    });

    reach.current = nearestD;

    // Written straight to the DOM: routing this through React state would
    // re-render the whole tree on every frame.
    markers.current?.forEach((el, i) => {
      if (!el) return;
      const q = projected[i];
      el.style.transform = `translate(-50%, -50%) translate(${q?.x ?? 0}px, ${q?.y ?? 0}px)`;
      el.style.setProperty("--open", String(opened[i] ?? 0));
      el.style.setProperty("--near", nearest === i && open.current > .5 ? "1" : "0");
      el.style.setProperty("--hue", String(t.hue));
      el.style.setProperty("--bubble", `${t.bubblePx}px`);
    });
  });

  return <group>
    {notes.map((note, i) => <mesh key={note.id} ref={el => { meshes.current[i] = el; }} frustumCulled={false}>
      <planeGeometry args={[1, 1]} />
      <shaderMaterial ref={el => { shaders.current[i] = el; }} {...templates[i]} {...BLEND}
        vertexShader={noteVertex} fragmentShader={noteFragment} />
    </mesh>)}
  </group>;
}
