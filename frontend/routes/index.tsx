import { Head } from "fresh/runtime";
import { define } from "../utils.ts";
import { listProjects, saveProject } from "../lib/kv.ts";
import { GitHubLink } from "../components/GitHubLink.tsx";
import { Logo } from "../components/Logo.tsx";
import ThemeToggle from "../islands/ThemeToggle.tsx";

interface Data {
  projects: Awaited<ReturnType<typeof listProjects>>;
}

function generatedTitle() {
  return `Project ${new Date().toLocaleString()}`;
}

export const handler = define.handlers({
  async GET(ctx): Promise<{ data: Data }> {
    const projects = await listProjects(ctx.state.session);
    return { data: { projects } };
  },

  async POST(ctx): Promise<Response> {
    const form = await ctx.req.formData();
    const title = (form.get("title")?.toString() ?? "").trim() ||
      generatedTitle();

    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const project = {
      id,
      title,
      createdAt: now,
      updatedAt: now,
      messages: [],
    };
    await saveProject(ctx.state.session, project);
    return ctx.redirect(`/projects/${id}`, 303);
  },
});

export default define.page<typeof handler>(function Home({ data }) {
  return (
    <>
      <Head>
        <title>FEDOT.MAS</title>
      </Head>
      <div class="home">
        <div class="home-top">
          <a href="/" class="nav-wordmark">
            <Logo size={22} />
            FEDOT.MAS
          </a>
          <div class="nav-right">
            <GitHubLink />
            <ThemeToggle />
          </div>
        </div>

        <main class="projects-home">
          <div class="home-head">
            <h2>Projects</h2>
            <form method="post" f-client-nav={false}>
              <button
                type="submit"
                class="fab"
                aria-label="New project"
                title="New project"
              >
                +
              </button>
            </form>
          </div>

          {data.projects.length === 0
            ? <p class="empty">No projects yet.</p>
            : (
              <div class="project-list">
                {data.projects.map((p) => (
                  <div key={p.id} class="project-card">
                    <a href={`/projects/${p.id}`} class="project-main">
                      <span class="project-title">{p.title}</span>
                      <time dateTime={p.updatedAt}>
                        {new Date(p.updatedAt).toLocaleString()}
                      </time>
                    </a>
                    <div class="project-actions">
                      <a
                        href={`/projects/${p.id}/rename`}
                        class="icon-btn"
                        aria-label="Rename"
                        title="Rename"
                      >
                        ✎
                      </a>
                      <form
                        method="post"
                        action={`/projects/${p.id}/delete`}
                        f-client-nav={false}
                      >
                        <button
                          type="submit"
                          class="icon-btn danger"
                          aria-label="Delete"
                          title="Delete"
                        >
                          ×
                        </button>
                      </form>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </main>
      </div>
    </>
  );
});
