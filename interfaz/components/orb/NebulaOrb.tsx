"use client";

import { useEffect, useRef } from "react";
import { clampEnergy, phases, type OrbSignal } from "@/lib/helios/state";
import { orbTargetScale } from "@/lib/helios/motion";

const MAX_FPS = 30;
const MAX_DPR = 1.4;
const HOVER_LIFT = 1.04;

export interface NebulaOrbProps {
  signal: OrbSignal;
  brightness?: number;
  motion?: boolean;
  sampleAmplitude?: (timeSeconds: number) => number;
  onExpansion?: (scale: number) => void;
  hovered?: { current: boolean };
}

const vertexShader = `#version 300 es
in vec2 p;
void main(){gl_Position=vec4(p,0.,1.);}`;

const fragmentShader = `#version 300 es
precision highp float;
out vec4 outColor;
uniform vec2 res;
uniform float time;
uniform float mode;
uniform float energy;
uniform float brightness;
uniform float orbScale;
uniform vec3 accent;

float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){
  vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1)),f.x),f.y);
}
float fbm(vec2 p){
  float v=0.,a=.5;mat2 m=mat2(.8,.6,-.6,.8);
  for(int i=0;i<5;i++){v+=a*noise(p);p=m*p*2.03+13.7;a*=.48;}
  return v;
}

void main(){
  vec2 uv=(gl_FragCoord.xy-.5*res)/min(res.x,res.y);
  float t=time*(.12+mode*.035);
  float rr=length(uv);
  float activity=.55+energy*.42;
  float radius=.314*orbScale+sin(t*1.15)*.00155*activity;
  float sd=rr-radius;
  // Fuera del halo no hay nada que dibujar: evita calcular cinco capas de
  // ruido sobre la mayor parte transparente del canvas.
  if(sd>.18){outColor=vec4(0.);return;}
  float body=1.-smoothstep(-.004,.008,sd);
  float q=clamp(rr/radius,0.,1.);
  float z=sqrt(max(0.,1.-q*q));
  float fresnel=pow(1.-z,2.15);

  vec3 cyan=mix(vec3(.04,.64,1.),accent,.18);
  vec3 ice=vec3(.62,.94,1.);
  vec3 violet=mix(vec3(.38,.16,.85),accent,.12);
  vec3 col=vec3(.0002,.0008,.0022);
  col+=body*vec3(.001,.004,.011);

  mat2 spin=mat2(cos(t*.23),-sin(t*.23),sin(t*.23),cos(t*.23));
  vec2 np=spin*(uv/radius)*2.25;
  float cloudA=fbm(np+vec2(t*.12,-t*.06));
  float cloudB=fbm(np*1.47+vec2(-t*.08,t*.11)+4.7);
  float cloudC=fbm(np*2.2+vec2(t*.045,t*.025)+11.2);
  float gas=smoothstep(.43,.74,cloudA*.58+cloudB*.3+cloudC*.12);
  float nebulaMask=smoothstep(.92,.18,q)*smoothstep(.04,.28,q);
  float lobe=.5+.5*sin(atan(np.y,np.x)*2.+cloudB*5.2-t*.8);
  vec3 nebula=mix(violet,cyan,smoothstep(.18,.86,cloudB+lobe*.18));
  col+=body*nebula*gas*nebulaMask*(.34+.08*activity);
  col+=body*ice*pow(gas,3.)*nebulaMask*.16;

  float nucleus=exp(-18.*dot(uv+vec2(.018,-.012),uv+vec2(.018,-.012)));
  nucleus*=.52+.48*fbm(np*1.55+vec2(-t*.09,t*.07));
  col+=body*mix(violet,ice,.58)*nucleus*(.11+.035*mode);

  vec2 cells=floor(np*18.);
  vec2 local=fract(np*18.)-.5;
  float dustSeed=hash(cells);
  float dust=(1.-smoothstep(.018,.075,length(local)))*step(.965,dustSeed);
  dust*=nebulaMask*(.35+.65*sin(t*1.3+dustSeed*24.)*.5+.325);
  col+=body*ice*dust*.36;
  col+=body*cyan*fresnel*(.075+.025*mode);

  float edge=exp(-abs(sd)*145.);
  float halo=exp(-abs(sd)*24.)*(1.-body*.58);
  col+=edge*mix(cyan,ice,.48)*(.43+.05*mode);
  col+=halo*cyan*.10;
  if(mode>2.5){float pulse=.45+.55*sin(t*8.-atan(uv.y,uv.x)*2.);col+=edge*ice*.15*pulse;}

  col=1.-exp(-col*(2.8*brightness));
  float opacity=clamp(body+halo*.45,0.,1.);
  outColor=vec4(col*opacity,opacity);
}`;

function makeShader(gl: WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("No se pudo crear el shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader) || "Shader no válido";
    gl.deleteShader(shader);
    throw new Error(message);
  }
  return shader;
}

function rgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.replace("#", ""), 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
}

const phaseMode = { idle: 0, listening: .5, thinking: 1, tool: 2, responding: 3, error: .2 } as const;

export function NebulaOrb({ signal, brightness = 1.8, motion = true, sampleAmplitude, onExpansion, hovered }: NebulaOrbProps) {
  const container = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const latest = useRef({ signal, brightness, motion, sampleAmplitude, onExpansion, hovered });
  latest.current = { signal, brightness, motion, sampleAmplitude, onExpansion, hovered };

  useEffect(() => {
    const element = canvas.current;
    const host = container.current;
    if (!element || !host) return;
    const gl = element.getContext("webgl2", { alpha: true, antialias: false, powerPreference: "low-power" });
    if (!gl) { host.dataset.failed = "true"; return; }

    let program: WebGLProgram | null = null;
    let buffer: WebGLBuffer | null = null;
    let frame = 0;
    let disposed = false;
    let inView = true;
    let currentMode = phaseMode[latest.current.signal.phase];
    let currentEnergy = latest.current.signal.energy;
    let currentScale = .96;
    let elapsed = 0;
    let previous = performance.now();
    let lastDraw = 0;
    let reportedScale = currentScale;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const intersection = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; }, { threshold: .01 });
    intersection.observe(host);

    try {
      program = gl.createProgram();
      if (!program) throw new Error("No se pudo crear el programa WebGL");
      const vertex = makeShader(gl, gl.VERTEX_SHADER, vertexShader);
      const fragment = makeShader(gl, gl.FRAGMENT_SHADER, fragmentShader);
      gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
      gl.deleteShader(vertex); gl.deleteShader(fragment);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "No se pudo enlazar el shader");
      gl.useProgram(program);
      buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl.STATIC_DRAW);
      const position = gl.getAttribLocation(program, "p");
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    } catch {
      host.dataset.failed = "true";
      if (program) gl.deleteProgram(program);
      if (buffer) gl.deleteBuffer(buffer);
      intersection.disconnect();
      return;
    }

    const uniform = (name: string) => gl.getUniformLocation(program!, name);
    const uniforms = {
      res: uniform("res"), time: uniform("time"), mode: uniform("mode"), energy: uniform("energy"),
      brightness: uniform("brightness"), orbScale: uniform("orbScale"), accent: uniform("accent"),
    };
    const draw = (now: number) => {
      if (disposed) return;
      frame = requestAnimationFrame(draw);
      if (!inView || document.hidden || now - lastDraw < 1000 / MAX_FPS) return;
      lastDraw = now;
      const props = latest.current;
      const animate = props.motion !== false && !reduced.matches;
      const dt = Math.min((now - previous) / 1000, .05);
      previous = now;
      if (animate) elapsed += dt;
      const targetMode = phaseMode[props.signal.phase];
      currentMode += (targetMode - currentMode) * (animate ? 1 - Math.exp(-dt * 3.5) : 1);
      currentEnergy += (clampEnergy(props.signal.energy) - currentEnergy) * (animate ? 1 - Math.exp(-dt * 2.4) : 1);
      const amplitude = animate && props.sampleAmplitude ? clampEnergy(props.sampleAmplitude(elapsed)) : 0;
      const targetScale = orbTargetScale(props.signal.phase, currentEnergy, amplitude, elapsed, animate);
      const hoverScale = props.hovered?.current ? HOVER_LIFT : 1;
      currentScale += (targetScale * hoverScale - currentScale) * (animate ? 1 - Math.exp(-dt * 8) : 1);
      if (props.onExpansion && Math.abs(currentScale - reportedScale) > .0008) {
        reportedScale = currentScale;
        props.onExpansion(currentScale);
      }

      const rect = element.getBoundingClientRect();
      // El núcleo es un shader por píxel. DPR 1.4 conserva la definición visual
      // sin pagar el coste del DPR 2 en una animación limitada a 30 FPS.
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      const width = Math.max(1, Math.floor(rect.width * dpr));
      const height = Math.max(1, Math.floor(rect.height * dpr));
      if (element.width !== width || element.height !== height) {
        element.width = width; element.height = height; gl.viewport(0, 0, width, height);
      }
      const accent = rgb(phases[props.signal.phase].color);
      gl.uniform2f(uniforms.res, width, height);
      gl.uniform1f(uniforms.time, elapsed);
      gl.uniform1f(uniforms.mode, currentMode);
      gl.uniform1f(uniforms.energy, currentEnergy);
      gl.uniform1f(uniforms.brightness, Math.max(.2, props.brightness / 1.8));
      gl.uniform1f(uniforms.orbScale, currentScale / .96);
      gl.uniform3f(uniforms.accent, accent[0], accent[1], accent[2]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      intersection.disconnect();
      if (buffer) gl.deleteBuffer(buffer);
      if (program) gl.deleteProgram(program);
    };
  }, []);

  return <div ref={container} className="orb-canvas nebula-orb" role="img" aria-label={`Núcleo nebuloso de Helios: ${phases[signal.phase].label}`}>
    <canvas ref={canvas} aria-hidden="true" />
    <div className="nebula-orb-fallback" aria-hidden="true" />
  </div>;
}
