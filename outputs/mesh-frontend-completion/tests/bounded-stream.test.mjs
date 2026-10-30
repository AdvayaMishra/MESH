import test from "node:test";
import assert from "node:assert/strict";
import {boundedEventStream} from "../lib/connected/bounded-stream.ts";

test("SSE passthrough preserves chunks and cleans up at end",async()=>{
 const abort=new AbortController();let cleaned=0;
 const source=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('data: {"ok":true}\n\n'));c.close();}});
 const stream=boundedEventStream(source,abort,()=>cleaned++);
 assert.equal(await new Response(stream).text(),'data: {"ok":true}\n\n');assert.equal(cleaned,1);assert.equal(abort.signal.aborted,false);
});
test("SSE byte limit aborts upstream without leaking its error",async()=>{
 const abort=new AbortController();let cleaned=0;
 const source=new ReadableStream({start(c){c.enqueue(new Uint8Array(10));}});
 await assert.rejects(new Response(boundedEventStream(source,abort,()=>cleaned++,3)).text(),/Stream interrupted/);
 assert.equal(abort.signal.aborted,true);assert.equal(cleaned,1);
});
test("SSE caller cancellation closes its upstream",async()=>{
 const abort=new AbortController();let cleaned=0,cancelled=0;
 const source=new ReadableStream({cancel(){cancelled++;}});
 await boundedEventStream(source,abort,()=>cleaned++).cancel();assert.equal(abort.signal.aborted,true);assert.equal(cleaned,1);assert.equal(cancelled,1);
});
test("SSE upstream failures are replaced with a safe interruption",async()=>{
 const abort=new AbortController();
 const source=new ReadableStream({start(c){c.error(new Error("private upstream diagnostic"));}});
 await assert.rejects(new Response(boundedEventStream(source,abort,()=>{})).text(),e=>e.message.includes("Stream interrupted")&&!e.message.includes("private"));
});
