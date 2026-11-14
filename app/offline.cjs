// Loaded in the OCR process and its workers. No network access for recognition.
const deny = () => { throw new Error('OCR_NETWORK_ACCESS_FORBIDDEN'); };
for (const name of ['http', 'https']) {
  const mod = require(name);
  mod.request = deny;
  mod.get = deny;
}
const net = require('net');
net.connect = deny;
net.createConnection = deny;
const dns = require('dns');
dns.lookup = deny;
dns.resolve = deny;
globalThis.fetch = deny;
