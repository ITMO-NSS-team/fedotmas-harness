import { useSignal } from "@preact/signals";
import { useEffect, useRef } from "preact/hooks";
import {
  EDGES,
  NODE_ATTRS,
  NODES,
  type NodeStatus,
  POS,
  RUN_EVENTS,
  type RunEvent,
} from "../lib/demoRun.ts";
import type { Message } from "../lib/kv.ts";

type RunState = "idle" | "running" | "done";

interface ConsoleProps {
  projectId: string;
  title: string;
  initialMessages: Message[];
}

const CHIPS = ["debate(3 experts)", "map → join(vote)", "planner → workers"];

const MIN_SCALE = 0.3;
const MAX_SCALE = 4;

export default function Console(
  { projectId, title, initialMessages }: ConsoleProps,
) {
  const runState = useSignal<RunState>("idle");
  const tick = useSignal(0);
  const nodeStatus = useSignal<Record<string, NodeStatus>>(
    Object.fromEntries(NODES.map((n) => [n, "pending"])) as Record<
      string,
      NodeStatus
    >,
  );
  const nodeHistory = useSignal<Record<string, string[]>>(
    Object.fromEntries(NODES.map((n) => [n, []])),
  );
  const transcript = useSignal<Message[]>(initialMessages);
  const inspecting = useSignal<string | null>(null);
  const inputValue = useSignal("");

  const graphCanvasRef = useRef<HTMLCanvasElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const nodePositions = useRef<Record<string, { x: number; y: number }>>({});
  const canvasSize = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  const drag = useRef<{
    node: string | null;
    offsetX: number;
    offsetY: number;
  }>({ node: null, offsetX: 0, offsetY: 0 });
  const pan = useRef<{
    active: boolean;
    sx: number;
    sy: number;
    stx: number;
    sty: number;
  }>({ active: false, sx: 0, sy: 0, stx: 0, sty: 0 });
  const timers = useRef<number[]>([]);
  const reducedMotion = useRef(false);

  const scale = useSignal(1);
  const tx = useSignal(0);
  const ty = useSignal(0);

  function cssSize(c: HTMLCanvasElement) {
    const r = c.parentElement!.getBoundingClientRect();
    return { w: r.width, h: r.height };
  }

  function sizeCanvas(c: HTMLCanvasElement) {
    const { w, h } = cssSize(c);
    const dpr = devicePixelRatio || 1;
    c.width = Math.max(1, w * dpr);
    c.height = Math.max(1, h * dpr);
    c.style.width = `${w}px`;
    c.style.height = `${h}px`;
  }

  function initPositions() {
    const c = graphCanvasRef.current;
    if (!c) return;
    const { w, h } = cssSize(c);
    const prev = canvasSize.current;
    const positions = nodePositions.current;

    if (prev.w === 0 || prev.h === 0 || Object.keys(positions).length === 0) {
      NODES.forEach((n) => {
        const [nx, ny] = POS[n];
        positions[n] = { x: nx * w, y: ny * h };
      });
    } else {
      // Scale existing positions proportionally to the new canvas size.
      const sx = w / prev.w;
      const sy = h / prev.h;
      NODES.forEach((n) => {
        const p = positions[n];
        if (p) {
          p.x *= sx;
          p.y *= sy;
        }
      });
    }

    canvasSize.current = { w, h };
  }

  function cssVar(name: string): string {
    if (typeof document === "undefined") return "#999999";
    return getComputedStyle(document.documentElement).getPropertyValue(name)
      .trim() ||
      "#999999";
  }

  function toWorld(sx: number, sy: number) {
    return {
      x: (sx - tx.value) / scale.value,
      y: (sy - ty.value) / scale.value,
    };
  }

  function clampZoom(s: number) {
    return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
  }

  function setZoomAround(newScale: number, sx: number, sy: number) {
    const clamped = clampZoom(newScale);
    const before = toWorld(sx, sy);
    tx.value = sx - before.x * clamped;
    ty.value = sy - before.y * clamped;
    scale.value = clamped;
    drawGraph();
  }

  function resetView() {
    scale.value = 1;
    tx.value = 0;
    ty.value = 0;
    drawGraph();
  }

  function drawGraph() {
    const c = graphCanvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const dpr = devicePixelRatio || 1;
    const w = c.width, h = c.height;
    if (!w || !h) return;
    ctx.clearRect(0, 0, w, h);

    initPositions();

    ctx.setTransform(
      scale.value * dpr,
      0,
      0,
      scale.value * dpr,
      tx.value * dpr,
      ty.value * dpr,
    );

    const positions = nodePositions.current;
    const status = nodeStatus.value;
    const insp = inspecting.value;
    const now = performance.now();
    const accent = cssVar("--accent");
    const good = cssVar("--good");
    const pending = cssVar("--graph-pending");
    const ink = cssVar("--ink");
    const soft = cssVar("--ink-soft");

    const paper = cssVar("--paper");

    ctx.lineWidth = 2;
    EDGES.forEach(({ from: a, to: b }) => {
      const bothDone = status[a] !== "pending" && status[b] !== "pending";
      const firing = status[a] === "active" || status[b] === "active";
      ctx.strokeStyle = firing ? accent : bothDone ? good : pending;
      ctx.globalAlpha = firing ? 0.6 : bothDone ? 0.4 : 0.28;
      ctx.beginPath();
      ctx.moveTo(positions[a].x, positions[a].y);
      ctx.lineTo(positions[b].x, positions[b].y);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;

    EDGES.forEach(({ from: a, to: b, label }) => {
      const t = 0.62;
      const mx = positions[a].x + (positions[b].x - positions[a].x) * t;
      const my = positions[a].y + (positions[b].y - positions[a].y) * t;
      ctx.font = "12px ui-monospace, Menlo, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      ctx.lineWidth = 4;
      ctx.strokeStyle = paper;
      ctx.strokeText(label, mx, my);
      ctx.fillStyle = ink;
      ctx.fillText(label, mx, my);
    });

    NODES.forEach((n) => {
      const s = status[n];
      const pulse = s === "active" && !reducedMotion.current
        ? 1 + 0.12 * Math.sin(now / 220)
        : 1;
      const baseR = 14;
      const r = baseR * pulse * (insp === n ? 1.25 : 1);
      const px = positions[n].x;
      const py = positions[n].y;

      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fillStyle = s === "ran" ? good : s === "active" ? accent : pending;
      ctx.fill();
      if (insp === n) {
        ctx.lineWidth = 3;
        ctx.strokeStyle = ink;
        ctx.stroke();
      }

      ctx.font = `13px ui-monospace, Menlo, monospace`;
      ctx.fillStyle = soft;
      ctx.textAlign = "center";
      ctx.fillText(n, px, py + baseR + 18);
    });

    if (runState.value === "running" && !reducedMotion.current) {
      requestAnimationFrame(drawGraph);
    }
  }

  function applyEvent(ev: RunEvent) {
    tick.value = ev.tick;

    const status = { ...nodeStatus.value };
    NODES.forEach((n) => {
      if (status[n] === "active" && !ev.active.includes(n)) status[n] = "ran";
    });
    ev.active.forEach((n) => (status[n] = ev.done ? "ran" : "active"));
    nodeStatus.value = status;

    const hist = { ...nodeHistory.value };
    Object.entries(ev.hist).forEach(([n, h]) => {
      hist[n] = [...hist[n], h];
    });
    nodeHistory.value = hist;

    if (ev.done) runState.value = "done";
    drawGraph();
  }

  function playLive() {
    runState.value = "running";
    let delay = 250;
    RUN_EVENTS.forEach((ev, i) => {
      delay += i === 0 ? 250 : 900;
      timers.current.push(setTimeout(() => applyEvent(ev), delay));
    });
  }

  async function persistMessage(msg: Message) {
    try {
      await fetch(`/api/projects/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(msg),
      });
    } catch (err) {
      console.error("Failed to persist message:", err);
    }
  }

  function addChat(text: string, role: "user" | "system"): Message {
    const msg: Message = {
      id: crypto.randomUUID(),
      role,
      text,
      createdAt: new Date().toISOString(),
    };
    transcript.value = [...transcript.value, msg];
    requestAnimationFrame(() => {
      const el = transcriptRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
    return msg;
  }

  function submit() {
    const val = inputValue.value.trim();
    if (!val) return;
    inputValue.value = "";
    const userMsg = addChat(val, "user");
    persistMessage(userMsg);
    if (transcript.value.length === 1) {
      addChat("Running", "system");
      playLive();
    }
    requestAnimationFrame(() => {
      const c = graphCanvasRef.current;
      if (c) {
        sizeCanvas(c);
        drawGraph();
      }
    });
  }

  useEffect(() => {
    reducedMotion.current =
      matchMedia("(prefers-reduced-motion: reduce)").matches;

    const graphObserver = new ResizeObserver(() => {
      const c = graphCanvasRef.current;
      if (c) {
        sizeCanvas(c);
        drawGraph();
      }
    });
    if (graphCanvasRef.current?.parentElement) {
      graphObserver.observe(graphCanvasRef.current.parentElement);
    }

    return () => {
      graphObserver.disconnect();
      timers.current.forEach(clearTimeout);
    };
    // deno-lint-ignore-next-line
  }, []);

  function nodeAt(sx: number, sy: number): string | null {
    const world = toWorld(sx, sy);
    const positions = nodePositions.current;
    for (const n of NODES) {
      const p = positions[n];
      if (p && Math.hypot(p.x - world.x, p.y - world.y) < 22) {
        return n;
      }
    }
    return null;
  }

  function handleWheel(e: WheelEvent) {
    e.preventDefault();
    const canvas = e.currentTarget as HTMLCanvasElement;
    const r = canvas.getBoundingClientRect();
    const sx = e.clientX - r.left;
    const sy = e.clientY - r.top;
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    setZoomAround(scale.value * factor, sx, sy);
  }

  function handlePointerDown(e: PointerEvent) {
    const canvas = e.currentTarget as HTMLCanvasElement;
    const r = canvas.getBoundingClientRect();
    const sx = e.clientX - r.left;
    const sy = e.clientY - r.top;
    const n = nodeAt(sx, sy);
    if (n) {
      const p = nodePositions.current[n];
      const world = toWorld(sx, sy);
      drag.current = {
        node: n,
        offsetX: world.x - p.x,
        offsetY: world.y - p.y,
      };
      inspecting.value = n;
      canvas.setPointerCapture(e.pointerId);
      drawGraph();
    } else {
      pan.current = {
        active: true,
        sx: e.clientX,
        sy: e.clientY,
        stx: tx.value,
        sty: ty.value,
      };
      canvas.setPointerCapture(e.pointerId);
    }
  }

  function handlePointerMove(e: PointerEvent) {
    if (drag.current.node) {
      const canvas = e.currentTarget as HTMLCanvasElement;
      const r = canvas.getBoundingClientRect();
      const sx = e.clientX - r.left;
      const sy = e.clientY - r.top;
      const world = toWorld(sx, sy);
      nodePositions.current[drag.current.node] = {
        x: world.x - drag.current.offsetX,
        y: world.y - drag.current.offsetY,
      };
      drawGraph();
      return;
    }
    if (pan.current.active) {
      tx.value = pan.current.stx + (e.clientX - pan.current.sx);
      ty.value = pan.current.sty + (e.clientY - pan.current.sy);
      drawGraph();
    }
  }

  function handlePointerUp(e: PointerEvent) {
    const canvas = e.currentTarget as HTMLCanvasElement;
    canvas.releasePointerCapture(e.pointerId);
    drag.current = { node: null, offsetX: 0, offsetY: 0 };
    pan.current = { active: false, sx: 0, sy: 0, stx: 0, sty: 0 };
  }

  function handleCanvasClick(e: MouseEvent) {
    const canvas = e.currentTarget as HTMLCanvasElement;
    const r = canvas.getBoundingClientRect();
    const sx = e.clientX - r.left;
    const sy = e.clientY - r.top;
    const n = nodeAt(sx, sy);
    if (n) inspecting.value = n;
  }

  const insp = inspecting.value;
  const inspAttrs = insp ? NODE_ATTRS[insp] : null;

  return (
    <div class="console" data-phase="workspace" data-run={runState.value}>
      <header class="topbar">
        <div class="project-head">
          <span class="project-title-tag">{title}</span>
          <span class="badge">
            <span class="pip" />
            {runState.value === "running"
              ? `live · superstep ${String(tick.value).padStart(2, "0")}`
              : runState.value === "done"
              ? `done · ${RUN_EVENTS.length} supersteps`
              : "idle"}
          </span>
        </div>
      </header>

      <div class="stage">
        <section class="graph-card">
          <div class="graph-head">
            <div class="tree">
              {NODES.map((n) => {
                const s = nodeStatus.value[n];
                const cls = s === "active"
                  ? "active"
                  : s === "ran"
                  ? "done-node"
                  : "";
                return (
                  <span
                    key={n}
                    class={`tree-node ${cls}`}
                    onClick={() => (inspecting.value = n)}
                  >
                    <span class="node-dot" />
                    {n}
                  </span>
                );
              })}
            </div>
            <div class="graph-tools">
              <div class="zoom-controls">
                <button
                  type="button"
                  class="zoom-btn"
                  onClick={() => {
                    const c = graphCanvasRef.current;
                    if (!c) return;
                    const r = c.getBoundingClientRect();
                    setZoomAround(scale.value * 1.2, r.width / 2, r.height / 2);
                  }}
                  aria-label="Zoom in"
                  title="Zoom in"
                >
                  +
                </button>
                <button
                  type="button"
                  class="zoom-btn"
                  onClick={() => {
                    const c = graphCanvasRef.current;
                    if (!c) return;
                    const r = c.getBoundingClientRect();
                    setZoomAround(scale.value * 0.8, r.width / 2, r.height / 2);
                  }}
                  aria-label="Zoom out"
                  title="Zoom out"
                >
                  −
                </button>
                <button
                  type="button"
                  class="zoom-btn"
                  onClick={resetView}
                  aria-label="Reset view"
                  title="Reset view"
                >
                  ⌂
                </button>
              </div>
              <a class="pill-link" href={`/projects/${projectId}/logs`}>
                log ↗
              </a>
            </div>
          </div>

          <div class="canvas-status">
            <span>
              {runState.value === "idle"
                ? "ready"
                : `superstep ${
                  String(tick.value).padStart(2, "0")
                } · ${NODES.length} nodes`}
            </span>
            <span>{runState.value === "done" ? "quiescent" : " "}</span>
          </div>

          <div class="canvas-wrap">
            <canvas
              class="graph-canvas"
              ref={graphCanvasRef}
              onClick={handleCanvasClick}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onWheel={handleWheel}
            />
            <div class="canvas-hint">
              drag nodes · drag canvas · scroll to zoom
            </div>
            {insp && inspAttrs && (
              <div class="node-inspector">
                <div class="ihead">
                  <b>{insp}</b>
                  <span class={`pill ${nodeStatus.value[insp]}`}>
                    {nodeStatus.value[insp] === "active"
                      ? "running"
                      : nodeStatus.value[insp] === "ran"
                      ? "done"
                      : "waiting"}
                  </span>
                  <button
                    type="button"
                    class="close-btn"
                    onClick={() => (inspecting.value = null)}
                  >
                    ×
                  </button>
                </div>
                <div class="inspect-body">
                  <div class="inspect-row">
                    <span class="inspect-key">kind</span>
                    <span class="inspect-val">{inspAttrs.kind}</span>
                  </div>
                  <div class="inspect-row">
                    <span class="inspect-key">reads</span>
                    <span class="inspect-val">
                      {inspAttrs.reads.join(", ")}
                    </span>
                  </div>
                  <div class="inspect-row">
                    <span class="inspect-key">writes</span>
                    <span class="inspect-val">
                      {inspAttrs.writes.join(", ")}
                    </span>
                  </div>
                  <div class="inspect-desc">{inspAttrs.description}</div>
                </div>
                <div class="inspect-hist">
                  {nodeHistory.value[insp].length
                    ? nodeHistory.value[insp].map((h, i) => (
                      <div key={i}>· {h}</div>
                    ))
                    : <div>· not started</div>}
                </div>
              </div>
            )}
          </div>
        </section>

        <section class="chat-col">
          <div class="transcript" ref={transcriptRef}>
            {transcript.value.map((m) => (
              <div
                key={m.id}
                class={`chat-msg ${m.role === "user" ? "user" : ""}`}
              >
                <span class="role">
                  {m.role === "user" ? "» you" : "# system"}
                </span>
                <br />
                {m.text}
              </div>
            ))}
          </div>

          <div class="composer-wrap">
            <div class="composer">
              <span class="caret">›</span>
              <input
                value={inputValue.value}
                onInput={(
                  e,
                ) => (inputValue.value = (e.target as HTMLInputElement).value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="Describe the task..."
              />
            </div>

            {transcript.value.length === 0 && runState.value !== "running" && (
              <div class="chips">
                {CHIPS.map((t) => (
                  <span
                    key={t}
                    class="chip"
                    onClick={() => {
                      inputValue.value = t;
                      submit();
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
