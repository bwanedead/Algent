import { fail, respond } from "./envelope";
import { dispatch } from "./router";

/** The one GET handler body behind /api/v1/*: dispatch, wrap in the envelope, map errors. */
export async function handleApi(req: Request, segments: string[]): Promise<Response> {
  try {
    const url = new URL(req.url);
    return respond(req, await dispatch(segments, url.searchParams));
  } catch (e) {
    return fail(e);
  }
}
