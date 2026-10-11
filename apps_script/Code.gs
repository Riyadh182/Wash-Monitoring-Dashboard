/**
 * Wash & Dry hourly log helper (Google Apps Script).
 * Install: in the Google Sheet -> Extensions -> Apps Script -> paste this file -> Save -> reload the sheet.
 * A "Wash Tools" menu appears. Run "Create rows for a day" at the start of every production day.
 *
 * It pre-fills Date, Hour, Unit and Machine/Process on Wash_Log and Dry_Log (hour by hour), so supervisors
 * only type numbers. Rows are ordered hour-major: all machines for hour 1, then hour 2, ... use a Filter on the Hour column.
 */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('Wash Tools')
    .addItem('Create rows for a day', 'createDayRows')
    .addItem('Protect key columns (warning only)', 'protectKeys')
    .addToUi();
}

function setting_(key, dflt) {
  const sh = SpreadsheetApp.getActive().getSheetByName('Settings');
  const vals = sh.getDataRange().getValues();
  for (let i = 1; i < vals.length; i++) if (String(vals[i][0]).trim() === key) return Number(vals[i][1]);
  return dflt;
}

function label_(startHour, i) {
  const p = n => ('0' + (n % 24)).slice(-2);
  return p(startHour + i) + ':00-' + p(startHour + i + 1) + ':00';
}

function createDayRows() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActive();
  const resp = ui.prompt('Production date (yyyy-mm-dd)', 'Example: 2026-10-08', ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const m = resp.getResponseText().trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (!m) { ui.alert('Please use yyyy-mm-dd'); return; }
  const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const startHour = setting_('Day_Start_Hour', 8);
  const tz = ss.getSpreadsheetTimeZone();
  const dateKey = Utilities.formatDate(date, tz, 'yyyy-MM-dd');

  const wash = ss.getSheetByName('Wash_Log'), dry = ss.getSheetByName('Dry_Log');
  [wash, dry].forEach(sh => sh.getRange('A:B').setNumberFormats(
    Array(sh.getMaxRows()).fill(['yyyy-mm-dd', '@'])));

  // duplicate guard
  const existing = wash.getLastRow() > 1 ? wash.getRange(2, 1, wash.getLastRow() - 1, 1).getValues() : [];
  for (const r of existing) {
    if (r[0] instanceof Date && Utilities.formatDate(r[0], tz, 'yyyy-MM-dd') === dateKey) {
      ui.alert('Rows for ' + dateKey + ' already exist in Wash_Log. Nothing was added.'); return;
    }
  }

  const mm = ss.getSheetByName('Master_Machine').getDataRange().getValues();   // Unit, Machine_ID, Type, Plan_per_hr, Active
  const mp = ss.getSheetByName('Master_Process').getDataRange().getValues();   // Unit, Process, Machines, Capacity_per_day, Active
  const machines = mm.slice(1).filter(r => r[1] && String(r[4]).toUpperCase() !== 'N');
  const procs = mp.slice(1).filter(r => r[1] && String(r[4]).toUpperCase() !== 'N');

  const wRows = [], dRows = [];
  for (let h = 0; h < 24; h++) {
    const lab = label_(startHour, h);
    machines.forEach(r => wRows.push([date, lab, r[0], r[1]]));
    procs.forEach(r => dRows.push([date, lab, r[0], r[1]]));
  }
  wash.getRange(wash.getLastRow() + 1, 1, wRows.length, 4).setValues(wRows);
  dry.getRange(dry.getLastRow() + 1, 1, dRows.length, 4).setValues(dRows);
  ui.alert('Created ' + wRows.length + ' wash rows and ' + dRows.length + ' dry rows for ' + dateKey +
           '. Tip: use Data > Create a filter and filter the Hour column.');
}

function protectKeys() {
  const ss = SpreadsheetApp.getActive();
  ['Wash_Log', 'Dry_Log'].forEach(n => {
    const sh = ss.getSheetByName(n);
    sh.getRange(1, 1, 1, sh.getMaxColumns()).protect().setWarningOnly(true);
    sh.getRange(2, 1, sh.getMaxRows() - 1, 4).protect().setWarningOnly(true);   // Date, Hour, Unit, Machine/Process
  });
  SpreadsheetApp.getUi().alert('Header row and key columns now show a warning if someone edits them.');
}
