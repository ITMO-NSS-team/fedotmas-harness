import { Head } from "fresh/runtime";
import { define } from "../utils.ts";
import Console from "../islands/Console.tsx";

export default define.page(function Home() {
  return (
    <>
      <Head>
        <title>fedotmas</title>
      </Head>
      <Console />
    </>
  );
});
