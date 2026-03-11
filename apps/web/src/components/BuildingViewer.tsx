"use client";

import { OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import type { ThreeEvent } from "@react-three/fiber";
import type { Hotspot } from "@buildingtalk/shared";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

type ViewerProps = {
  hotspots: Hotspot[];
  activeHotspotIds: string[];
  debugMode: boolean;
  modelUrl: string;
};

type CameraPose = {
  position: THREE.Vector3;
  target: THREE.Vector3;
  fov: number;
};

type CameraAnimation = {
  fromPos: THREE.Vector3;
  toPos: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toTarget: THREE.Vector3;
  fromFov: number;
  toFov: number;
  startMs: number;
  durationMs: number;
};

type DebugUpdate = {
  hoveredMesh?: string | null;
  cameraPose?: string;
};

type SceneProps = ViewerProps & {
  onDebugUpdate: (update: DebugUpdate) => void;
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function easeInOut(t: number): number {
  if (t < 0.5) {
    return 4 * t * t * t;
  }
  return 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function parseBBox(hotspot: Hotspot): THREE.Box3 | null {
  if (!hotspot.bbox?.min || !hotspot.bbox?.max) {
    return null;
  }
  return new THREE.Box3(
    new THREE.Vector3(...hotspot.bbox.min),
    new THREE.Vector3(...hotspot.bbox.max),
  );
}

function Scene({ hotspots, activeHotspotIds, debugMode, onDebugUpdate, modelUrl }: SceneProps) {
  const { camera } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const animRef = useRef<CameraAnimation | null>(null);
  const lastDebugTick = useRef(0);

  const { scene } = useGLTF(modelUrl);
  const perspectiveCamera = camera as THREE.PerspectiveCamera;
  const defaultMaterial = useRef(
    new Map<
      string,
      {
        emissive: THREE.Color;
        emissiveIntensity: number;
      }
    >(),
  );

  const hotspotById = useMemo(() => {
    return new Map(hotspots.map((h) => [h.id, h]));
  }, [hotspots]);

  const primaryHotspot = activeHotspotIds.length ? hotspotById.get(activeHotspotIds[0]) : null;

  const activeBBoxes = useMemo(() => {
    return activeHotspotIds
      .map((id) => hotspotById.get(id))
      .filter((v): v is Hotspot => Boolean(v))
      .map((hotspot) => ({ id: hotspot.id, box: parseBBox(hotspot) }))
      .filter((entry): entry is { id: string; box: THREE.Box3 } => entry.box !== null);
  }, [activeHotspotIds, hotspotById]);

  const meshIndex = useMemo(() => {
    const byName = new Map<string, THREE.Mesh[]>();
    scene.traverse((obj) => {
      if ((obj as THREE.Mesh).isMesh) {
        const mesh = obj as THREE.Mesh;
        const key = mesh.name || "(unnamed)";
        if (!byName.has(key)) {
          byName.set(key, []);
        }
        byName.get(key)?.push(mesh);
      }
    });
    return byName;
  }, [scene]);

  useEffect(() => {
    scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh || !mesh.material) {
        return;
      }

      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of materials) {
        const standard = material as THREE.MeshStandardMaterial;
        if (typeof standard.emissiveIntensity !== "number" || !standard.emissive) {
          continue;
        }

        if (!defaultMaterial.current.has(standard.uuid)) {
          defaultMaterial.current.set(standard.uuid, {
            emissive: standard.emissive.clone(),
            emissiveIntensity: standard.emissiveIntensity,
          });
        }
      }
    });
  }, [scene]);

  useEffect(() => {
    scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh || !mesh.material) {
        return;
      }

      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const material of materials) {
        const standard = material as THREE.MeshStandardMaterial;
        const defaults = defaultMaterial.current.get(standard.uuid);
        if (defaults) {
          standard.emissive.copy(defaults.emissive);
          standard.emissiveIntensity = defaults.emissiveIntensity;
        }
      }
    });

    const meshNames = new Set<string>();
    for (const id of activeHotspotIds) {
      const hotspot = hotspotById.get(id);
      hotspot?.meshNames?.forEach((name) => meshNames.add(name));
    }

    for (const meshName of meshNames) {
      const meshes = meshIndex.get(meshName) || [];
      for (const mesh of meshes) {
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const material of materials) {
          const standard = material as THREE.MeshStandardMaterial;
          if (!standard.emissive) {
            continue;
          }
          standard.emissive.set("#f08428");
          standard.emissiveIntensity = 0.45;
        }
      }
    }
  }, [scene, activeHotspotIds, hotspotById, meshIndex]);

  useEffect(() => {
    if (!primaryHotspot || !controlsRef.current) {
      return;
    }

    const controls = controlsRef.current;
    let toPose: CameraPose | null = null;

    if (primaryHotspot.camera) {
      toPose = {
        position: new THREE.Vector3(...primaryHotspot.camera.position),
        target: new THREE.Vector3(...primaryHotspot.camera.target),
        fov: primaryHotspot.camera.fov,
      };
    }

    if (!toPose) {
      const bbox = parseBBox(primaryHotspot);
      if (bbox) {
        const center = bbox.getCenter(new THREE.Vector3());
        const size = bbox.getSize(new THREE.Vector3()).length();
        const offset = Math.max(12, size * 1.2);
        toPose = {
          position: center.clone().add(new THREE.Vector3(offset, offset * 0.4, offset)),
          target: center,
          fov: 45,
        };
      }
    }

    if (!toPose && primaryHotspot.meshNames?.length) {
      const bbox = new THREE.Box3();
      let hasAny = false;
      for (const name of primaryHotspot.meshNames) {
        const meshes = meshIndex.get(name) || [];
        for (const mesh of meshes) {
          hasAny = true;
          bbox.union(new THREE.Box3().setFromObject(mesh));
        }
      }
      if (hasAny) {
        const center = bbox.getCenter(new THREE.Vector3());
        const size = bbox.getSize(new THREE.Vector3()).length();
        const offset = Math.max(12, size * 1.1);
        toPose = {
          position: center.clone().add(new THREE.Vector3(offset, offset * 0.35, offset)),
          target: center,
          fov: 45,
        };
      }
    }

    if (!toPose) {
      return;
    }

    animRef.current = {
      fromPos: camera.position.clone(),
      toPos: toPose.position,
      fromTarget: controls.target.clone(),
      toTarget: toPose.target,
      fromFov: perspectiveCamera.fov,
      toFov: toPose.fov,
      startMs: performance.now(),
      durationMs: 1400,
    };
  }, [camera, meshIndex, primaryHotspot]);

  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls) {
      return;
    }

    const anim = animRef.current;
    if (anim) {
      const elapsed = performance.now() - anim.startMs;
      const t = Math.min(1, elapsed / anim.durationMs);
      const eased = easeInOut(t);

      camera.position.set(
        lerp(anim.fromPos.x, anim.toPos.x, eased),
        lerp(anim.fromPos.y, anim.toPos.y, eased),
        lerp(anim.fromPos.z, anim.toPos.z, eased),
      );

      controls.target.set(
        lerp(anim.fromTarget.x, anim.toTarget.x, eased),
        lerp(anim.fromTarget.y, anim.toTarget.y, eased),
        lerp(anim.fromTarget.z, anim.toTarget.z, eased),
      );

      perspectiveCamera.fov = lerp(anim.fromFov, anim.toFov, eased);
      perspectiveCamera.updateProjectionMatrix();

      if (t >= 1) {
        animRef.current = null;
      }
    }

    controls.update();

    if (debugMode) {
      const now = performance.now();
      if (now - lastDebugTick.current >= 180) {
        lastDebugTick.current = now;
        onDebugUpdate({
          cameraPose:
            `position=[${camera.position.x.toFixed(2)}, ${camera.position.y.toFixed(2)}, ${camera.position.z.toFixed(2)}]\n` +
            `target=[${controls.target.x.toFixed(2)}, ${controls.target.y.toFixed(2)}, ${controls.target.z.toFixed(2)}]\n` +
            `fov=${perspectiveCamera.fov.toFixed(1)}`,
        });
      }
    }
  });

  return (
    <>
      <ambientLight intensity={0.7} />
      <directionalLight position={[20, 25, 12]} intensity={1.0} />
      <directionalLight position={[-14, 10, -9]} intensity={0.35} />

      {debugMode && <axesHelper args={[20]} />}
      {debugMode && <gridHelper args={[220, 44, "#b6ad99", "#d7cfbf"]} position={[0, -0.8, 0]} />}

      <primitive
        object={scene}
        onPointerMove={(event: ThreeEvent<PointerEvent>) => {
          if (!debugMode) {
            return;
          }
          const objectName = (event.object as THREE.Object3D).name || "(unnamed mesh)";
          onDebugUpdate({ hoveredMesh: objectName });
        }}
        onPointerOut={() => {
          if (debugMode) {
            onDebugUpdate({ hoveredMesh: null });
          }
        }}
      />

      {activeBBoxes.map((entry) => {
        const center = entry.box.getCenter(new THREE.Vector3());
        const size = entry.box.getSize(new THREE.Vector3());
        return (
          <mesh key={entry.id} position={center.toArray()}>
            <boxGeometry args={[size.x, size.y, size.z]} />
            <meshStandardMaterial color="#d77039" transparent opacity={0.2} />
          </mesh>
        );
      })}

      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.06}
        minDistance={8}
        maxDistance={220}
        maxPolarAngle={Math.PI / 2.05}
      />
    </>
  );
}

export default function BuildingViewer(props: ViewerProps) {
  const [hoveredMesh, setHoveredMesh] = useState<string | null>(null);
  const [cameraPose, setCameraPose] = useState<string>("");

  return (
    <div className="relative h-full w-full overflow-hidden rounded-3xl border border-black/10 bg-[#f7f1e2] shadow-panel">
      <Canvas camera={{ position: [45, 16, 45], fov: 50 }}>
        <Suspense fallback={null}>
          <Scene
            {...props}
            onDebugUpdate={(update) => {
              if (typeof update.hoveredMesh !== "undefined") {
                setHoveredMesh(update.hoveredMesh);
              }
              if (typeof update.cameraPose !== "undefined") {
                setCameraPose(update.cameraPose);
              }
            }}
          />
        </Suspense>
      </Canvas>

      <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-black/55 px-3 py-2 text-xs text-white">
        {props.debugMode ? "Debug mode enabled" : "Viewer"}
      </div>

      {props.debugMode && (
        <div className="absolute bottom-3 left-3 max-w-[340px] rounded-lg border border-white/30 bg-black/60 p-3 text-[11px] text-white">
          <div className="mb-2 font-semibold">Debug Inspector</div>
          <div className="mb-2">Hovered mesh: {hoveredMesh || "(none)"}</div>
          <pre className="mb-2 whitespace-pre-wrap rounded bg-black/35 p-2 text-[10px]">{cameraPose || "(waiting)"}</pre>
          <button
            type="button"
            className="pointer-events-auto rounded border border-white/30 px-2 py-1 text-[10px] hover:bg-white/15"
            onClick={() => {
              if (!cameraPose) {
                return;
              }
              navigator.clipboard.writeText(cameraPose).catch(() => undefined);
            }}
          >
            Copy Pose
          </button>
        </div>
      )}
    </div>
  );
}

useGLTF.preload("/models/palace.glb");
