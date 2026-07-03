import { Head } from "fresh/runtime";
import { define } from "../../../utils.ts";
import { getProject } from "../../../lib/kv.ts";
import { RUN_EVENTS } from "../../../lib/demoRun.ts";

interface Data {
  project: NonNullable<Awaited<ReturnType<typeof getProject>>>;
}

export const handler = define.handlers({
  async GET(ctx) {
    const project = await getProject(ctx.state.session, ctx.params.id);
    if (!project) {
      return ctx.redirect("/", 303);
    }
    return { data: { project } };
  },
});

export default define.page<typeof handler>(function ProjectLogsPage(
  { data },
) {
  const lines = RUN_EVENTS.flatMap((ev) =>
    ev.logs.map((msg) => ({ tick: ev.tick, msg }))
  );

  return (
    <>
      <Head>
        <title>FEDOT.MAS · {data.project.title} · log</title>
      </Head>
      <div class="logs-page">
        <div class="logs-top">
          <a href={`/projects/${data.project.id}`}>← {data.project.title}</a>
          <span>run #204 — debate(3 experts)</span>
        </div>
        <div class="logs-wrap">
          <div class="logs-panel">
            <p class="logs-note">
              static demo log — live stream will appear once fedotmas-web is
              wired up
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
