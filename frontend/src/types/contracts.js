/** @typedef {{id:number, title:string, payload:object, author:string}} BusinessCase */
/** @typedef {{id:number, case_id:number, status:'queued'|'running'|'complete'|'failed'}} Run */
/** @typedef {{id:number, run_id:number, digest:string, report:{summary:string, metrics:object, sections:Array}}} Evidence */
/** @typedef {{id:number, ingredient:string, lot:string, status:'active'|'sealed', sealed_by:string, sealed_at:string}} Lot */
/** @typedef {{id:number, batch:string, kind:'semi'|'dish', recipe:string, name:string, status:'produced'|'served', served_by:string, served_at:string}} Production */
