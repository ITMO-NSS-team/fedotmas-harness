import { useSignal } from "@preact/signals";
import { useEffect, useRef } from "preact/hooks";
import { Logo } from "../components/Logo.tsx";
import {
  EDGES,
  NODES,
  type NodeStatus,
  POS,
  RUN_EVENTS,
  type RunEvent,
} from "../lib/demoRun.ts";

type Phase = "compose" | "workspace";
type RunState = "idle" | "running" | "done";

const CHIPS = ["debate(3 эксперта)", "map → join(vote)", "planner → workers"];

export default function Console() {
  const phase = useSignal<Phase>("compose");
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
  const transcript = useSignal<{ user: boolean; text: string }[]>([]);
  const inspecting = useSignal<string | null>(null);
  const inputValue = useSignal("");

  const idleCanvasRef = useRef<HTMLCanvasElement>(null);
  const graphCanvasRef = useRef<HTMLCanvasElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const lastPos = useRef<Record<string, { x: number; y: number }>>({});
  const timers = useRef<number[]>([]);
  const reducedMotion = useRef(false);

  function sizeCanvas(c: HTMLCanvasElement) {
    const r = c.parentElement!.getBoundingClientRect();
    const dpr = devicePixelRatio || 1;
    c.width = Math.max(1, r.width * dpr);
    c.height = Math.max(1, r.height * dpr);
    c.style.width = `${r.width}px`;
    c.style.height = `${r.height}px`;
  }

  function drawIdle() {
    const c = idleCanvasRef.current;
    if (!c) return;
    sizeCanvas(c);
    const ctx = c.getContext("2d")!;
    const dpr = devicePixelRatio || 1;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.strokeStyle = "rgba(163,154,134,0.22)";
    ctx.fillStyle = "rgba(163,154,134,0.32)";
    for (let i = 0; i < 6; i++) {
      const cx = Math.random() * c.width, cy = Math.random() * c.height;
      const n = 2 + Math.floor(Math.random() * 2);
      const pts = Array.from({ length: n }, () => ({
        x: cx + (Math.random() - 0.5) * 90 * dpr,
        y: cy + (Math.random() - 0.5) * 90 * dpr,
      }));
      for (let a = 0; a < pts.length; a++) {
        for (let b = a + 1; b < pts.length; b++) {
          ctx.beginPath();
          ctx.moveTo(pts[a].x, pts[a].y);
          ctx.lineTo(pts[b].x, pts[b].y);
          ctx.stroke();
        }
      }
      pts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2.4 * dpr, 0, Math.PI * 2);
        ctx.fill();
      });
    }
  }

  function drawGraph() {
    const c = graphCanvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const w = c.width, h = c.height;
    if (!w || !h) return;
    const dpr = devicePixelRatio || 1;
    ctx.clearRect(0, 0, w, h);

    const pos: Record<string, { x: number; y: number }> = {};
    NODES.forEach((n) => {
      const [x, y] = POS[n];
      pos[n] = { x: x * w, y: y * h };
    });
    lastPos.current = pos;

    const status = nodeStatus.value;
    const insp = inspecting.value;
    const now = performance.now();

    ctx.lineWidth = 1.4 * dpr;
    EDGES.forEach(([a, b]) => {
      const bothDone = status[a] !== "pending" && status[b] !== "pending";
      const firing = status[a] === "active" || status[b] === "active";
      ctx.strokeStyle = firing
        ? "rgba(96,130,182,0.6)"
        : bothDone
        ? "rgba(76,138,99,0.4)"
        : "rgba(163,154,134,0.28)";
      ctx.beginPath();
      ctx.moveTo(pos[a].x, pos[a].y);
      ctx.lineTo(pos[b].x, pos[b].y);
      ctx.stroke();
    });

    NODES.forEach((n) => {
      const s = status[n];
      const pulse = s === "active" && !reducedMotion.current
        ? 1 + 0.12 * Math.sin(now / 220)
        : 1;
      const r = 10 * dpr * pulse * (insp === n ? 1.25 : 1);
      ctx.beginPath();
      ctx.arc(pos[n].x, pos[n].y, r, 0, Math.PI * 2);
      ctx.fillStyle = s === "ran"
        ? "#4c8a63"
        : s === "active"
        ? "#6082b6"
        : "#c9bd9e";
      ctx.fill();
      if (insp === n) {
        ctx.lineWidth = 2 * dpr;
        ctx.strokeStyle = "#26231d";
        ctx.stroke();
      }
      ctx.font = `${11 * dpr}px ui-monospace, Menlo, monospace`;
      ctx.fillStyle = "#6b6355";
      ctx.textAlign = "center";
      ctx.fillText(n, pos[n].x, pos[n].y + 26 * dpr);
    });

    if (runState.value === "running" && !reducedMotion.current) {
      requestAnimationFrame(drawGraph);
    }
  }

  // one function applies a superstep delta whether it arrives on a timer
  // (a live run) or all at once (replaying a saved to_graph) — same contract either way.
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

  function playInstant() {
    RUN_EVENTS.forEach(applyEvent);
  }

  function addChat(text: string, user: boolean) {
    transcript.value = [...transcript.value, { user, text }];
    requestAnimationFrame(() => {
      const el = transcriptRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  function enterWorkspace(firstMessage: string, ack: string) {
    phase.value = "workspace";
    transcript.value = [];
    addChat(firstMessage, true);
    addChat(ack, false);
    requestAnimationFrame(() => {
      const c = graphCanvasRef.current;
      if (c) sizeCanvas(c);
      drawGraph();
    });
  }

  function submit() {
    const val = inputValue.value.trim();
    if (!val) return;
    inputValue.value = "";
    if (phase.value === "compose") {
      enterWorkspace(val, "запускаю прогон · граф — слева, полный лог — /logs");
      playLive();
    } else {
      addChat(val, true);
    }
  }

  function openReplay() {
    enterWorkspace(
      "debate(3 эксперта) — прогон #204",
      "загружаю сохранённый to_graph — без запуска, чистые данные",
    );
    playInstant();
  }

  useEffect(() => {
    reducedMotion.current =
      matchMedia("(prefers-reduced-motion: reduce)").matches;
    drawIdle();

    // the graph card's width animates in via CSS (0 -> 68%), so a one-off
    // size read on mount would race the transition and land on 0. A
    // ResizeObserver re-measures on every frame of that animation instead.
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

    const idleObserver = new ResizeObserver(() => {
      if (phase.value === "compose") drawIdle();
    });
    if (idleCanvasRef.current?.parentElement) {
      idleObserver.observe(idleCanvasRef.current.parentElement);
    }

    return () => {
      graphObserver.disconnect();
      idleObserver.disconnect();
      timers.current.forEach(clearTimeout);
    };
    // deno-lint-ignore-next-line
  }, []);

  function handleCanvasClick(e: MouseEvent) {
    const canvas = e.currentTarget as HTMLCanvasElement;
    const r = canvas.getBoundingClientRect();
    const dpr = devicePixelRatio || 1;
    const x = (e.clientX - r.left) * dpr, y = (e.clientY - r.top) * dpr;
    for (const n of NODES) {
      const p = lastPos.current[n];
      if (p && Math.hypot(p.x - x, p.y - y) < 18 * dpr) {
        inspecting.value = n;
        return;
      }
    }
  }

  const insp = inspecting.value;

  return (
    <div class="console" data-phase={phase.value} data-run={runState.value}>
      <header class="topbar">
        <div class="wordmark">
          <Logo size={22} />
          fedot<span class="dot">·</span>mas
          <span class="badge">
            <span class="pip" />
            {runState.value === "running"
              ? `live · superstep ${String(tick.value).padStart(2, "0")}`
              : runState.value === "done"
              ? `done · ${RUN_EVENTS.length} supersteps`
              : "idle"}
          </span>
        </div>
        <div class="contract-note">одна страница · один поток</div>
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
            <a class="pill-link" href="/logs">run log ↗</a>
          </div>

          <div class="canvas-status">
            <span>
              {runState.value === "idle"
                ? "готов к запуску"
                : `superstep ${
                  String(tick.value).padStart(2, "0")
                } · ${NODES.length} узлов`}
            </span>
            <span>{runState.value === "done" ? "quiescent" : " "}</span>
          </div>

          <div class="canvas-wrap">
            <canvas
              class="graph-canvas"
              ref={graphCanvasRef}
              onClick={handleCanvasClick}
            />
            <div class="canvas-hint">клик по узлу — история и статус</div>
            {insp && (
              <div class="node-inspector">
                <div class="ihead">
                  <b>{insp}</b>
                  <span class={`pill ${nodeStatus.value[insp]}`}>
                    {nodeStatus.value[insp] === "active"
                      ? "выполняется"
                      : nodeStatus.value[insp] === "ran"
                      ? "отработал"
                      : "ожидает"}
                  </span>
                  <button
                    type="button"
                    class="close-btn"
                    onClick={() => (inspecting.value = null)}
                  >
                    ×
                  </button>
                </div>
                <div class="inspect-hist">
                  {nodeHistory.value[insp].length
                    ? nodeHistory.value[insp].map((h, i) => (
                      <div key={i}>· {h}</div>
                    ))
                    : <div>· ещё не запускался</div>}
                </div>
              </div>
            )}
          </div>
        </section>

        <section class="chat-col">
          {phase.value === "compose" && (
            <>
              <canvas class="idle-canvas" ref={idleCanvasRef} />
              <div class="hero">
                <div class="hero-mark">
                  <Logo size={56} />
                </div>
                <h1>
                  fedot<span class="dot">·</span>mas
                </h1>
                <p class="tag">
                  опишите задачу — граф выполнения появится слева
                </p>
              </div>
            </>
          )}

          {phase.value === "workspace" && (
            <div class="transcript" ref={transcriptRef}>
              {transcript.value.map((m, i) => (
                <div key={i} class={`chat-msg ${m.user ? "user" : ""}`}>
                  <span class="role">{m.user ? "» вы" : "# fedotmas"}</span>
                  <br />
                  {m.text}
                </div>
              ))}
            </div>
          )}

          <div class="composer-wrap">
            <div class="composer">
              <span class="caret">›</span>
              <input
                value={inputValue.value}
                onInput={(
                  e,
                ) => (inputValue.value = (e.target as HTMLInputElement).value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && submit()}
                placeholder="суммируй эти 40 отчётов и найди противоречия"
              />
              {phase.value === "compose" && (
                <button type="button" class="run-btn" onClick={submit}>
                  run ↵
                </button>
              )}
            </div>

            {phase.value === "compose" && (
              <>
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
                <button type="button" class="replay-link" onClick={openReplay}>
                  или открыть завершённый прогон →
                </button>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
