/**
 * feedback_sheet.gs — Google Apps Script web app that appends one row per
 * answer rating to the Sheet it is bound to. The backend POSTs here when
 * FEEDBACK_WEBHOOK_URL is set (backend/main.py, /api/feedback).
 *
 * Setup (once):
 *   1. Create a Google Sheet, e.g. "Maintenance Assistant — Feedback".
 *   2. Extensions > Apps Script, replace the code with this file, Save.
 *   3. Deploy > New deployment > type "Web app":
 *        Execute as: Me      Who has access: Anyone
 *   4. Copy the web app URL (ends in /exec) and set it on Render as
 *      FEEDBACK_WEBHOOK_URL. Keep it private: anyone with it can add rows.
 *
 * Re-deploying after an edit: Deploy > Manage deployments > edit > New version
 * (keeps the same URL).
 */
var COLUMNS = [
  "timestamp", "rating", "reasons", "note", "correction", "question", "answer",
  "provider", "sources", "values_suppressed", "request_id", "message_id",
];

function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(COLUMNS);
    sheet.setFrozenRows(1);
  }
  var data = JSON.parse(e.postData.contents);
  sheet.appendRow(COLUMNS.map(function (c) {
    var v = data[c];
    return v === undefined || v === null ? "" : v;
  }));
  return ContentService.createTextOutput("ok");
}
