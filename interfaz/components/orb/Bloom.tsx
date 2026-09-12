"use client";

import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Vector2 } from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

/** Original HDR bloom, using EffectComposer's correctly sized native target. */
export function Bloom() {
  const { gl, scene, camera, size, viewport, invalidate } = useThree();
  const composer = useRef<EffectComposer | null>(null);
  useEffect(() => {
    const pipeline = new EffectComposer(gl);
    // Full resolution: on a transparent canvas the bloom pass carries alpha too,
    // and upscaling a half-resolution alpha leaves a blocky dark fringe around
    // the sphere. The sprites are cheap now, so the extra fill is affordable.
    pipeline.setPixelRatio(gl.getPixelRatio());
    const render = new RenderPass(scene, camera);
    const bloom = new UnrealBloomPass(new Vector2(1, 1), .5, .72, .8);
    (bloom.highPassUniforms as { smoothWidth: { value: number } }).smoothWidth.value = .45;
    const output = new OutputPass();
    pipeline.addPass(render);
    pipeline.addPass(bloom);
    pipeline.addPass(output);
    composer.current = pipeline;
    invalidate();
    return () => {
      composer.current = null;
      render.dispose();
      bloom.dispose();
      output.dispose();
      pipeline.dispose();
    };
  }, [gl, scene, camera, invalidate]);
  useEffect(() => {
    composer.current?.setPixelRatio(viewport.dpr);
    composer.current?.setSize(size.width, size.height);
    invalidate();
  }, [size.width, size.height, viewport.dpr, invalidate]);
  useFrame((state, delta) => {
    if (composer.current) composer.current.render(delta);
    else state.gl.render(state.scene, state.camera);
  }, 1);
  return null;
}
