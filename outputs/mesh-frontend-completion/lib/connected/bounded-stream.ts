/** Bounded passthrough; never forwards upstream cookies, headers or error bodies. */
export function boundedEventStream(source:ReadableStream<Uint8Array>,controller:AbortController,cleanup:()=>void,maxBytes=2097152){
 const reader=source.getReader();let bytes=0,finished=false;
 function finish(){if(!finished){finished=true;cleanup();}}
 return new ReadableStream<Uint8Array>({
  async pull(destination){
   try{
    const next=await reader.read();
    if(next.done){finish();destination.close();return;}
    bytes+=next.value.byteLength;
    if(bytes>maxBytes)throw new Error("Stream limit");
    destination.enqueue(next.value);
   }catch{controller.abort();await reader.cancel().catch(()=>{});finish();destination.error(new Error("Stream interrupted. Refresh the saved result before retrying."));}
  },
  async cancel(){controller.abort();await reader.cancel().catch(()=>{});finish();},
 });
}
