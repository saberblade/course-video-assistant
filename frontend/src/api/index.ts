import { isMock } from "./http";
import { mockApi } from "./mock";
import { realApi } from "./videos";

export const api = isMock ? mockApi : realApi;
export { isMock } from "./http";
