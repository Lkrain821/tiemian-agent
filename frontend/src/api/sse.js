import { ApiError, apiUrl, readJson } from "./http.js";

export async function postSse(path, body, { idempotencyKey, signal, onEvent }) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify(body),
      signal
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError({
      code: "NETWORK_ERROR",
      message: "事件流连接失败，请稍后重试",
      data: { recoverable: true, cause: error?.message }
    });
  }

  if (!response.ok) {
    const payload = await readJson(response);
    throw new ApiError({
      code: payload.code,
      message: payload.message,
      data: payload.data,
      status: response.status
    });
  }
  if (!response.body) {
    throw new ApiError({
      code: "STREAM_UNAVAILABLE",
      message: "浏览器无法读取面试事件流",
      data: { recoverable: true }
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let receivedDone = false;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = parseEventBlock(block);
      if (!event) continue;
      if (event.envelope?.data?.schema_version !== 1) {
        throw new ApiError({
          code: "UNSUPPORTED_STREAM_SCHEMA",
          message: "事件协议版本不兼容，请刷新页面",
          data: { recoverable: true }
        });
      }
      await onEvent(event.envelope, event.type, event.id);
      if (event.type === "stream.done") receivedDone = true;
    }
    if (done) break;
  }

  if (!receivedDone) {
    throw new ApiError({
      code: "STREAM_DISCONNECTED",
      message: "事件流意外中断，正在恢复面试状态",
      data: { recoverable: true }
    });
  }
}

function parseEventBlock(block) {
  if (!block.trim() || block.trimStart().startsWith(":")) return null;
  let type = "message";
  let id = null;
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { type, id, envelope: JSON.parse(dataLines.join("\n")) };
  } catch {
    throw new ApiError({
      code: "INVALID_STREAM_EVENT",
      message: "收到无法识别的面试事件",
      data: { recoverable: true }
    });
  }
}
