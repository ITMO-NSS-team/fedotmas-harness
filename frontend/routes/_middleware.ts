import { getCookies, setCookie } from "@std/http";
import { define } from "../utils.ts";

export default define.middleware(async (ctx) => {
  const cookies = getCookies(ctx.req.headers);
  let session = cookies.session;
  if (!session) {
    session = crypto.randomUUID();
  }
  ctx.state.session = session;

  const response = await ctx.next();

  if (!cookies.session) {
    setCookie(response.headers, {
      name: "session",
      value: session,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    });
  }

  return response;
});
