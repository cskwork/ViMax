// Downloads the first <video> through the browser context's authenticated
// request. This carries cookies and avoids CORS limitations from in-page fetch.
page => (async () => {
  const src = await page.evaluate(() => {
    const videos = [...document.querySelectorAll('video')];
    const el = videos.find(video => video.currentSrc || video.src);
    return el ? (el.currentSrc || el.src) : null;
  });
  if (!src) return 'ERR:no-video';
  const resp = await page.context().request.get(src);
  if (!resp.ok()) return 'ERR:http-' + resp.status();
  const buf = await resp.body();
  return buf.toString('base64');
})()
