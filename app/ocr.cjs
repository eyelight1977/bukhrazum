// Narrow experiment runner; reads image jobs only, never visual_reference.json.
const fs = require('fs');
const path = require('path');
const { performance } = require('perf_hooks');
const moduleRoot = process.env.OCR_NODE_MODULES;
const tessPath = moduleRoot ? path.join(moduleRoot, 'tesseract.js') : 'tesseract.js';
const { createWorker } = require(tessPath);
const resolvedTess = require.resolve(tessPath);
const base = path.dirname(require.resolve(path.join(path.dirname(resolvedTess), '../package.json')));
const corePath = path.dirname(require.resolve('tesseract.js-core/package.json', { paths: [base] }));
const here = __dirname;
const [jobsPath, outputPath] = process.argv.slice(2);
if (!jobsPath || !outputPath) throw new Error('Usage: recognize.cjs jobs.json output.json');
(async () => {
  const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
  const started = performance.now();
  const worker = await createWorker(['rus', 'eng'], 1, {
    langPath: process.env.OCR_MODELS_DIR || path.join(here, 'models'), gzip: false, cacheMethod: 'none',
    corePath, workerPath: path.join(base, 'src/worker-script/node/index.js'),
  });
  const results = [];
  try {
    for (const job of jobs) {
      const start = performance.now();
      await worker.setParameters({
        tessedit_pageseg_mode: String(job.psm ?? 6),
        tessedit_char_whitelist: job.whitelist ?? '',
        preserve_interword_spaces: '1', user_defined_dpi: '300',
      });
      const { data } = await worker.recognize(path.resolve(job.image), {}, {text:true, tsv:true, blocks:true});
      results.push({...job, text:data.text, confidence:data.confidence, tsv:data.tsv, blocks:data.blocks,
        duration_ms:Math.round(performance.now()-start)});
    }
    fs.writeFileSync(outputPath, JSON.stringify({engine:'Tesseract.js', version:require(path.join(base,'package.json')).version,
      core_version:require(path.join(corePath,'package.json')).version, node:process.version,
      network:'blocked by offline.cjs in main process and worker threads',
      total_duration_ms:Math.round(performance.now()-started), results},null,2));
  } finally { await worker.terminate(); }
})().catch(error => { process.stderr.write(`${error.stack}\n`); process.exitCode=1; });
