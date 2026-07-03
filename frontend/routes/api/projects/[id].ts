import { define } from "../../../utils.ts";
import { appendMessage, getProject } from "../../../lib/kv.ts";
import type { Message } from "../../../lib/kv.ts";

export const handler = define.handlers({
  async GET(ctx) {
    const project = await getProject(ctx.state.session, ctx.params.id);
    if (!project) {
      return Response.json({ error: "not found" }, { status: 404 });
    }
    return Response.json(project);
  },

  async POST(ctx) {
    const body = await ctx.req.json() as Message;
    const message: Message = {
      id: body.id ?? crypto.randomUUID(),
      role: body.role === "system" ? "system" : "user",
      text: String(body.text ?? ""),
      createdAt: body.createdAt ?? new Date().toISOString(),
    };
    const updated = await appendMessage(
      ctx.state.session,
      ctx.params.id,
      message,
    );
    if (!updated) {
      return Response.json({ error: "not found" }, { status: 404 });
    }
    return Response.json(updated);
  },
});
