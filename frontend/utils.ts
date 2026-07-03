import { createDefine } from "fresh";

export type State = Record<string, never>;

export const define = createDefine<State>();
