import { Head } from "fresh/runtime";
import { define } from "../../../utils.ts";
import { getProject, saveProject } from "../../../lib/kv.ts";

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

  async POST(ctx) {
    const project = await getProject(ctx.state.session, ctx.params.id);
    if (!project) {
      return ctx.redirect("/", 303);
    }

    const form = await ctx.req.formData();
    const title = (form.get("title")?.toString() ?? "").trim() ||
      project.title;

    project.title = title;
    project.updatedAt = new Date().toISOString();
    await saveProject(ctx.state.session, project);
    return ctx.redirect(`/projects/${project.id}`, 303);
  },
});

export default define.page<typeof handler>(function RenamePage({ data }) {
  return (
    <>
      <Head>
        <title>FEDOT.MAS · Rename · {data.project.title}</title>
      </Head>
      <div class="home">
        <main class="welcome">
          <h1>Rename project</h1>
          <form
            method="post"
            class="home-create"
            f-client-nav={false}
          >
            <input
              name="title"
              defaultValue={data.project.title}
              placeholder="Project title..."
              autocomplete="off"
              autofocus
            />
            <button type="submit">Save</button>
          </form>
          <a href="/" class="text-link">← back</a>
        </main>
      </div>
    </>
  );
});
