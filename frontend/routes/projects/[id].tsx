import { Head } from "fresh/runtime";
import { define } from "../../utils.ts";
import { getProject } from "../../lib/kv.ts";
import Console from "../../islands/Console.tsx";

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

export default define.page<typeof handler>(function ProjectPage({ data }) {
  return (
    <>
      <Head>
        <title>FEDOT.MAS · {data.project.title}</title>
      </Head>
      <Console
        projectId={data.project.id}
        title={data.project.title}
        initialMessages={data.project.messages}
      />
    </>
  );
});
