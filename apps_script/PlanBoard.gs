/**
 * Plan Board tools (Google Sheets).  Paste into Extensions > Apps Script, save, reload the sheet.
 * Menu "Plan Board":
 *   1. Enable audit + plan history  (once per Sheet: installs the edit trigger and takes the first snapshot)
 *   2. Setup month                  (hides day blocks beyond the month length)
 *   3. Acknowledge edits            (marks Audit_Log rows as acknowledged; cells stay red)
 *   4. Create next month sheet      (copy with open orders only, opening balances carried, days cleared)
 * Layout contract (do not change): header rows 1-6, grand total row 7, data from row 8, codes in row 4, dates in row 3.
 */
var SHEET = 'Plan_Board', FIRST_ROW = 8, LAST_ROW = 707, CODE_ROW = 4, DATE_ROW = 3;
var DAY_START_COL = 32, DAY_BLOCK = 7, MAX_DAYS = 31;
var PLAN_FIELDS = ['Plan_Start', 'Plan_End', 'CRD', 'Revised_CRD', 'Order_Qty'];       // -> Plan_History (every change, incl. the first entry)
var DAY_PLAN = ['SEW_PLAN', 'WASH_PLAN'];                                              // -> Plan_History (re-planning is allowed, but recorded)
var LOCKED = ['SEW_ACT', 'WASH_ACT', 'Open_Received', 'Open_Washed', 'Open_Sew_Var', 'Open_Wash_Var', 'Wash_Reject', 'Missing_Body'];   // changing an entered value = EDIT (red)
var STATIC_CODES = ['Wash_Plant', 'Sewing_Unit', 'Buyer', 'Style', 'PO', 'Item', 'Color', 'Season', 'CRD', 'Revised_CRD', 'Order_Qty', 'Plan_Start', 'Plan_End', 'Merchant',
  'Open_Received', 'Open_Washed', 'Open_Sew_Var', 'Open_Wash_Var', 'First_Received_On', 'Wash_Reject', 'Missing_Body'];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Plan Board')
    .addItem('1. Enable audit + plan history', 'enableAudit')
    .addItem('2. Setup month (hide unused days)', 'setupMonth')
    .addItem('3. Acknowledge edits', 'acknowledgeEdits')
    .addItem('4. Create next month sheet', 'createNextMonth')
    .addToUi();
}

// ------------------------------------------------------------------ helpers
function codes_(sh) {
  var n = DAY_START_COL + MAX_DAYS * DAY_BLOCK - 1;
  return sh.getRange(CODE_ROW, 1, 1, n).getValues()[0];
}
function stamp_() { return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'); }
function isoDate_(v) { return v instanceof Date ? Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd') : (v === '' || v === null ? '' : String(v)); }
function norm_(v) { return v instanceof Date ? isoDate_(v) : (v === null || v === undefined ? '' : String(v).trim()); }
function shadow_(ss, create) {
  var sh = ss.getSheetByName('_Shadow');
  if (!sh && create) { sh = ss.insertSheet('_Shadow'); sh.hideSheet(); }
  return sh;
}
function appendRows_(ss, name, rows) {
  if (!rows.length) return;
  var sh = ss.getSheetByName(name);
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
}

// ------------------------------------------------------------------ 1. audit
function enableAudit() {
  var ss = SpreadsheetApp.getActive(), ui = SpreadsheetApp.getUi();
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'auditEdit') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('auditEdit').forSpreadsheet(ss).onEdit().create();
  snapshot_();
  ui.alert('Audit is ON. Numbers already in the sheet count as "entered": changing them later turns the cell red and is logged in Audit_Log. Plan dates / CRD / qty changes go to Plan_History.');
}
function snapshot_() {
  var ss = SpreadsheetApp.getActive(), sh = ss.getSheetByName(SHEET), sd = shadow_(ss, true);
  var n = DAY_START_COL + MAX_DAYS * DAY_BLOCK - 1;
  var vals = sh.getRange(FIRST_ROW, 1, LAST_ROW - FIRST_ROW + 1, n).getValues().map(function (r) { return r.map(norm_); });
  sd.clear();
  sd.getRange(1, 1, vals.length, n).setValues(vals);          // shadow row i <-> sheet row i + FIRST_ROW - 1
}

/** Installable onEdit trigger. Compares the edited range with the shadow copy so pastes of many cells are handled too. */
function auditEdit(e) {
  var rg = e.range, sh = rg.getSheet();
  if (sh.getName() !== SHEET) return;
  var r0 = Math.max(rg.getRow(), FIRST_ROW), r1 = Math.min(rg.getLastRow(), LAST_ROW);
  if (r1 < r0) return;
  var c0 = rg.getColumn(), c1 = rg.getLastColumn();
  var ss = e.source, sd = shadow_(ss, true);
  var cells = (r1 - r0 + 1) * (c1 - c0 + 1);
  var codes = codes_(sh), dates = sh.getRange(DATE_ROW, 1, 1, codes.length).getValues()[0];
  var cur = sh.getRange(r0, c0, r1 - r0 + 1, c1 - c0 + 1).getValues();
  var old = sd.getRange(r0 - FIRST_ROW + 1, c0, r1 - r0 + 1, c1 - c0 + 1).getValues();
  var user = (e.user && e.user.getEmail()) || Session.getActiveUser().getEmail() || '';
  var ts = stamp_(), today = new Date(); today.setHours(0, 0, 0, 0);
  var audit = [], hist = [], bulk = cells > 3000;
  for (var i = 0; i < cur.length; i++) {
    var row = r0 + i;
    var key = sh.getRange(row, 1, 1, 7).getValues()[0];       // A..G: plant, sewing, buyer, style, PO, item, color
    var plant = key[0], style = key[3], po = key[4], color = key[6];
    for (var j = 0; j < cur[i].length; j++) {
      var col = c0 + j, code = codes[col - 1];
      if (!code) continue;
      var nv = norm_(cur[i][j]), ov = norm_(old[i][j]);
      if (nv === ov) continue;
      var isDay = col >= DAY_START_COL;
      var dstr = isDay ? isoDate_(dates[col - 1]) : '';
      if (PLAN_FIELDS.indexOf(code) >= 0 || (isDay && DAY_PLAN.indexOf(code) >= 0)) {
        var field = isDay ? code + ' ' + dstr : code;
        hist.push([ts, user, plant, style, po, color, field, ov, nv, 0]);
      } else if (LOCKED.indexOf(code) >= 0 || (isDay && (code === 'SEW_ACT' || code === 'WASH_ACT'))) {
        if (ov !== '') {                                       // an entered number was changed or deleted -> manipulation
          audit.push([ts, user, plant, style, po, color, code, dstr, ov, nv, 'EDIT', '']);
          if (!bulk) { var c = sh.getRange(row, col); c.setBackground('#FF0000').setFontColor('#FFFFFF'); c.setNote('Edited ' + ts + ' by ' + (user || 'unknown') + '\nOld: ' + ov + '  New: ' + nv); }
        } else if (isDay && dstr && new Date(dstr) < new Date(today.getTime() - 86400000)) {
          audit.push([ts, user, plant, style, po, color, code, dstr, '', nv, 'LATE', '']);   // first entry for a day older than yesterday
        }
      }
    }
  }
  if (bulk) audit.push([ts, user, '', '(bulk)', '', '', 'RANGE', '', '', cells + ' cells', 'EDIT', '']);
  // plan history version numbers
  if (hist.length) {
    var hs = ss.getSheetByName('Plan_History'), data = hs.getLastRow() > 1 ? hs.getRange(2, 1, hs.getLastRow() - 1, 10).getValues() : [];
    hist.forEach(function (h) {
      var n = 0;
      data.forEach(function (d) { if (d[2] === h[2] && d[3] === h[3] && d[4] === h[4] && d[5] === h[5] && String(d[6]) === h[6]) n++; });
      h[9] = n + 1; data.push(h);
    });
    appendRows_(ss, 'Plan_History', hist);
  }
  appendRows_(ss, 'Audit_Log', audit);
  sd.getRange(r0 - FIRST_ROW + 1, c0, r1 - r0 + 1, c1 - c0 + 1).setValues(cur.map(function (r) { return r.map(norm_); }));
}

function acknowledgeEdits() {
  var ss = SpreadsheetApp.getActive(), sh = ss.getSheetByName('Audit_Log');
  var n = sh.getLastRow() - 1; if (n < 1) return;
  var rg = sh.getRange(2, 12, n, 1), v = rg.getValues(), who = Session.getActiveUser().getEmail() || 'ack', t = stamp_();
  rg.setValues(v.map(function (x) { return [x[0] === '' ? 'ACK ' + who + ' ' + t : x[0]]; }));
  SpreadsheetApp.getUi().alert('Acknowledged. Cells stay red as proof; the dashboard shows the audit rows as acknowledged.');
}

// ------------------------------------------------------------------ 2. month length
function setupMonth() {
  var ss = SpreadsheetApp.getActive(), sh = ss.getSheetByName(SHEET);
  var first = sh.getRange('B2').getValue();
  if (!(first instanceof Date)) { SpreadsheetApp.getUi().alert('Cell B2 must hold the first day of the month, e.g. 2026-11-01'); return; }
  var nd = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  for (var d = 1; d <= MAX_DAYS; d++) {
    var c = DAY_START_COL + (d - 1) * DAY_BLOCK;
    if (d <= nd) sh.showColumns(c, DAY_BLOCK); else sh.hideColumns(c, DAY_BLOCK);
  }
  SpreadsheetApp.getUi().alert('Month has ' + nd + ' days. Day blocks ' + (nd + 1) + '-' + MAX_DAYS + ' are hidden.');
}

// ------------------------------------------------------------------ 4. next month
function createNextMonth() {
  var ui = SpreadsheetApp.getUi(), ss = SpreadsheetApp.getActive(), sh = ss.getSheetByName(SHEET);
  var first = sh.getRange('B2').getValue();
  var next = new Date(first.getFullYear(), first.getMonth() + 1, 1);
  var tag = Utilities.formatDate(next, Session.getScriptTimeZone(), 'yyyy-MM');
  if (ui.alert('Create the ' + tag + ' sheet from this one? Only open orders are carried.', ui.ButtonSet.YES_NO) !== ui.Button.YES) return;
  var codes = codes_(sh), nCols = codes.length, idx = {};
  codes.forEach(function (c, i) { if (c && !(c in idx)) idx[c] = i; });
  var data = sh.getRange(FIRST_ROW, 1, LAST_ROW - FIRST_ROW + 1, nCols).getValues();
  var keep = [];
  data.forEach(function (r) {
    if (!r[idx.PO] || String(r[idx.Style]).toUpperCase().indexOf('EXAMPLE') === 0) return;
    var qty = Number(r[idx.Order_Qty]) || 0, sp = 0, sa = 0, wp = 0, wa = 0, firstRecv = '';
    for (var d = 0; d < MAX_DAYS; d++) {
      var b = DAY_START_COL - 1 + d * DAY_BLOCK;
      sp += Number(r[b]) || 0; sa += Number(r[b + 1]) || 0; wp += Number(r[b + 3]) || 0; wa += Number(r[b + 4]) || 0;
      if (!firstRecv && Number(r[b + 1]) > 0) firstRecv = sh.getRange(DATE_ROW, b + 1).getValue();
    }
    var recv = (Number(r[idx.Open_Received]) || 0) + sa, wash = (Number(r[idx.Open_Washed]) || 0) + wa;
    var rej = Number(r[idx.Wash_Reject]) || 0, miss = Number(r[idx.Missing_Body]) || 0;
    var balance = qty - wash, wip = recv - wash - rej - miss;
    if (balance <= 0.02 * qty && wip <= 0.02 * qty) return;           // finished, do not carry
    var o = r.slice(0, STATIC_CODES.length);
    o[idx.Open_Received] = recv; o[idx.Open_Washed] = wash;
    o[idx.Open_Sew_Var] = (Number(r[idx.Open_Received]) + Number(r[idx.Open_Sew_Var] || 0) + sp) - recv;       // plan minus actual at month end (+ = behind)
    o[idx.Open_Wash_Var] = (Number(r[idx.Open_Washed]) + Number(r[idx.Open_Wash_Var] || 0) + wp) - wash;
    o[idx.First_Received_On] = r[idx.First_Received_On] || (Number(r[idx.Open_Received]) > 0 ? r[idx.Plan_Start] : firstRecv);
    o[idx.Wash_Reject] = rej; o[idx.Missing_Body] = miss;
    keep.push(o);
  });
  var copy = ss.copy(ss.getName().replace(/\d{4}-\d{2}/, tag) + (ss.getName().match(/\d{4}-\d{2}/) ? '' : ' ' + tag));
  var csh = copy.getSheetByName(SHEET);
  csh.getRange('B2').setValue(next);
  var nS = STATIC_CODES.length;
  csh.getRange(FIRST_ROW, 1, LAST_ROW - FIRST_ROW + 1, nS).clearContent().setBackground(null).clearNote().setFontColor(null);
  csh.getRange(FIRST_ROW, DAY_START_COL, LAST_ROW - FIRST_ROW + 1, MAX_DAYS * DAY_BLOCK).clearContent().setBackground(null).clearNote().setFontColor(null);
  if (keep.length) csh.getRange(FIRST_ROW, 1, keep.length, nS).setValues(keep);
  csh.getRange(FIRST_ROW, 1, LAST_ROW - FIRST_ROW + 1, nS).setBackground('#FFF9DB');
  ['Audit_Log'].forEach(function (n) { var s = copy.getSheetByName(n); if (s && s.getLastRow() > 1) s.getRange(2, 1, s.getLastRow() - 1, s.getLastColumn()).clearContent(); });
  var sd = copy.getSheetByName('_Shadow'); if (sd) copy.deleteSheet(sd);
  ui.alert('Created: ' + copy.getUrl() + '\n\nIn the new sheet run Plan Board > 2. Setup month and 1. Enable audit.\nSecrets: add "' + Utilities.formatDate(first, Session.getScriptTimeZone(), 'yyyy-MM') + ':' + ss.getId() + '" to archive and put ' + copy.getId() + ' in current.');
}
