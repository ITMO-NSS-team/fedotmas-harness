import { define } from "../../../utils.ts";
import { listProjects } from "../../../lib/kv.ts";

export const handler = define.handlers({
  async GET(ctx) {
    const projects = await listProjects(ctx.state.session);
    return Response.json(projects);
  },
});
