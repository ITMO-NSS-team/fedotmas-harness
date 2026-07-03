import { define } from "../../../utils.ts";
import { deleteProject } from "../../../lib/kv.ts";

export const handler = define.handlers({
  async POST(ctx) {
    await deleteProject(ctx.state.session, ctx.params.id);
    return ctx.redirect("/", 303);
  },
});
