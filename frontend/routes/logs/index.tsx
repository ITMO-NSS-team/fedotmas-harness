import { Head } from "fresh/runtime";
import { define } from "../../utils.ts";
import { RUN_EVENTS } from "../../lib/demoRun.ts";

export default define.page(function LogsPage() {
  const lines = RUN_EVENTS.flatMap((ev) =>
    ev.logs.map((msg) => ({ tick: ev.tick, msg }))
  );

  return (
    <>
      <Head>
        <title>fedotmas — run log</title>
      </Head>
      <div class="logs-page">
        <div class="logs-top">
          <a href="/">← fedot·mas</a>
          <span>run #204 — debate(3 эксперта)</span>
        </div>
        <div class="logs-wrap">
          <div class="logs-panel">
            <p class="logs-note">
              статичный демонстрационный лог — живой стрим появится, когда
              заработает fedotmas-web
            </p>
            {lines.map((l, i) => (
              <div class="log-line" key={i}>
                <span class="t">12:0{i}</span>
                <span class="lvl-run">[{String(l.tick).padStart(2, "0")}]</span>
                <span>{l.msg}</span>
              </div>
            ))}
            <div class="log-line">
              <span class="log-cursor" />
            </div>
          </div>
        </div>
      </div>
    </>
  );
});
