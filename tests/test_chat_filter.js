/**
 * tests/test_chat_filter.js
 * Unit tests for chat message visibility logic (msgVisible).
 *
 * Run with: node tests/test_chat_filter.js
 *
 * Guards against:
 *  - DM conversation view showing 0 messages for broadcast-only nodes
 *  - chatSenderFilter not matching due to ! prefix format differences
 *  - timeFilter cutting off messages incorrectly
 *  - System messages showing/hiding logic
 */

'use strict';

let passed = 0, failed = 0;
function assert(cond, name) {
  if (cond) { console.log(`  ✓ ${name}`); passed++; }
  else       { console.error(`  ✗ FAIL: ${name}`); failed++; }
}

// ── Minimal stubs mimicking browser globals ─────────────────────
let activeConv      = 'all';
let chatSenderFilter = null;
let timeFilter      = 86400;
let showSystem      = true;

const BROADCAST_IDS = new Set(['ffffffff','4294967295','']);

function msgConvKey(msg) {
  const dest = String(msg.destination_id || '').toLowerCase();
  const isBroadcastDest = !dest || BROADCAST_IDS.has(dest);
  const hasChannel = msg.channel !== undefined && msg.channel !== null && Number(msg.channel) >= 0;
  if ((msg.type === 'tx' || msg.type === 'ai') && !isBroadcastDest)
    return `dm:${msg.destination_id}`;
  if (msg.type === 'rx' && !isBroadcastDest && msg.sender_id
      && myNodeId && dest === myNodeId)
    return `dm:${msg.sender_id}`;
  if (hasChannel) return `ch:${Number(msg.channel)}`;
  return 'system';
}

let myNodeId = 'ffaf8db4';

// ── msgVisible (copy-paste from templates/index.html) ───────────
function msgVisible(msg) {
  const now = Date.now()/1000;
  if (timeFilter > 0 && (now - msg.timestamp) > timeFilter) return false;
  if ((msg.type === 'system' || msg.type === 'error') && !showSystem) return false;
  if (msg.type === 'system' || msg.type === 'error') return activeConv === 'all' && !chatSenderFilter;

  const sid = (msg.sender_id      || '').replace(/^!/, '').toLowerCase();
  const did = (msg.destination_id || '').replace(/^!/, '').toLowerCase();

  if (chatSenderFilter) {
    const cf = chatSenderFilter.replace(/^!/, '').toLowerCase();
    return sid === cf || did === cf;
  }

  if (activeConv === 'all') return true;

  if (activeConv.startsWith('dm:')) {
    const peerId = activeConv.slice(3).toLowerCase();
    return sid === peerId || did === peerId;
  }

  return msgConvKey(msg) === activeConv;
}

// ── Test fixtures ────────────────────────────────────────────────
const NOW = Math.floor(Date.now() / 1000);

const broadcastFromA = {
  type: 'rx', channel: 0,
  sender_id: 'aabbccdd', destination_id: 'ffffffff',
  timestamp: NOW - 100, text: 'hello everyone'
};
const dmFromA = {
  type: 'rx', channel: 0,
  sender_id: 'aabbccdd', destination_id: 'ffaf8db4',
  timestamp: NOW - 200, text: '!stats'
};
const txToA = {
  type: 'tx', channel: 0,
  sender_id: 'ffaf8db4', destination_id: 'aabbccdd',
  timestamp: NOW - 50, text: 'Stats: ...'
};
const broadcastFromB = {
  type: 'rx', channel: 0,
  sender_id: '11223344', destination_id: 'ffffffff',
  timestamp: NOW - 60, text: 'hi from B'
};
const systemMsg = {
  type: 'system', channel: -1,
  sender_id: '', destination_id: '',
  timestamp: NOW - 10, text: 'Connected'
};
const oldMsg = {
  type: 'rx', channel: 0,
  sender_id: 'aabbccdd', destination_id: 'ffffffff',
  timestamp: NOW - 90000, text: 'old message'
};

// ── Test suite ───────────────────────────────────────────────────
function reset() {
  activeConv       = 'all';
  chatSenderFilter = null;
  timeFilter       = 86400;
  showSystem       = true;
}

console.log('\n=== activeConv = "all" (default) ===');
reset();
assert(msgVisible(broadcastFromA),  'broadcast msg visible in all view');
assert(msgVisible(dmFromA),          'dm rx msg visible in all view');
assert(msgVisible(txToA),            'tx msg visible in all view');
assert(msgVisible(systemMsg),        'system msg visible in all view');

console.log('\n=== DM conversation view — broadcast-only node (v5.79 regression test) ===');
reset();
activeConv = 'dm:aabbccdd';
// KEY TEST: broadcast messages from node A must be visible in dm:aabbccdd view
assert(msgVisible(broadcastFromA),  'broadcast from A visible in dm:aabbccdd (regression: was 0 msgs)');
assert(msgVisible(dmFromA),          'private dm from A visible in dm:aabbccdd');
assert(msgVisible(txToA),            'outgoing tx to A visible in dm:aabbccdd');
assert(!msgVisible(broadcastFromB), 'broadcast from B NOT visible in dm:aabbccdd');
assert(!msgVisible(systemMsg),       'system msg NOT visible in dm view');

console.log('\n=== DM conversation view — node B (no messages) ===');
reset();
activeConv = 'dm:11223344';
assert(msgVisible(broadcastFromB),  'broadcast from B visible in dm:11223344');
assert(!msgVisible(broadcastFromA), 'broadcast from A NOT visible in dm:11223344');
assert(!msgVisible(txToA),           'tx to A NOT visible in dm:11223344');

console.log('\n=== chatSenderFilter — set by clicking sender name ===');
reset();
chatSenderFilter = 'aabbccdd';
assert(msgVisible(broadcastFromA),  'broadcast from A visible with senderFilter=aabbccdd');
assert(msgVisible(dmFromA),          'dm from A visible with senderFilter=aabbccdd');
assert(msgVisible(txToA),            'tx to A visible with senderFilter=aabbccdd');
assert(!msgVisible(broadcastFromB), 'B messages NOT visible with senderFilter=aabbccdd');
assert(!msgVisible(systemMsg),       'system NOT visible with senderFilter active');

console.log('\n=== chatSenderFilter — ! prefix normalization ===');
reset();
chatSenderFilter = '!aabbccdd';  // with ! prefix
assert(msgVisible(broadcastFromA),  '! prefix normalized — broadcast from aabbccdd visible');
assert(!msgVisible(broadcastFromB), '! prefix normalized — B still excluded');

const msgWithBangId = { ...broadcastFromA, sender_id: '!aabbccdd' };
chatSenderFilter = 'aabbccdd';
assert(msgVisible(msgWithBangId),   'msg with !-prefixed sender_id matches filter without !');

console.log('\n=== timeFilter ===');
reset();
timeFilter = 3600;  // 1 hour
assert(msgVisible(broadcastFromA),  'recent message passes 1h filter');
assert(!msgVisible(oldMsg),          'old message (25h) hidden by 1h filter');

timeFilter = 0;  // All
assert(msgVisible(oldMsg),           'timeFilter=0 shows all ages');

console.log('\n=== System messages toggle ===');
reset();
showSystem = true;
assert(msgVisible(systemMsg),        'system visible when showSystem=true');
showSystem = false;
assert(!msgVisible(systemMsg),       'system hidden when showSystem=false');

// System msg must NOT show in dm view even when showSystem=true
reset();
showSystem = true;
activeConv = 'dm:aabbccdd';
assert(!msgVisible(systemMsg),       'system NOT shown in dm conversation view');

console.log('\n=== ch: conversation filter ===');
reset();
activeConv = 'ch:0';
assert(msgVisible(broadcastFromA),  'ch:0 broadcast visible in ch:0 view');
assert(!msgVisible(systemMsg),       'system NOT visible in ch:0 view');

console.log('\n');
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else             { console.log('ALL TESTS PASSED'); }
