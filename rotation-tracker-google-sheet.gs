// --- CONFIGURATION ---
const SINGER_COLUMN = 2;    // B
const STATUS_COLUMN = 4;    // D
const ROUND_COLUMN = 5;     // E
const NOTES_COLUMN = 6;     // F
const TIMESTAMP_COLUMN = 1; // A
// ---------------------

/**
 * Automatically populates Timestamp, Status, and Round when a new singer is added.
 */
function onEdit(e) {
  const sheet = e.source.getActiveSheet();
  const editedCell = e.range;

  if (editedCell.getColumn() === SINGER_COLUMN && editedCell.getRow() > 1 && sheet.getRange(editedCell.getRow(), TIMESTAMP_COLUMN).getValue() === '') {
    const newRow = editedCell.getRow();
    sheet.getRange(newRow, TIMESTAMP_COLUMN).setValue(new Date());
    sheet.getRange(newRow, STATUS_COLUMN).setValue('Waiting');
    sheet.getRange(newRow, ROUND_COLUMN).setFormula(`=COUNTIF($B$2:$B${newRow}, B${newRow})`);
  }
}

/**
 * Main function for the "Done" button. Marks the current singer as done and advances the queue.
 */
function markAsDone() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const ui = SpreadsheetApp.getUi();
  const data = sheet.getDataRange().getValues();

  const nowSingingInfo = findRowByStatus(data, "Now Singing");
  const upNextInfo = findRowByStatus(data, "Up Next");

  if (!nowSingingInfo) {
    ui.alert('Action Failed', 'Could not find a singer with the status "Now Singing".', ui.ButtonSet.OK);
    return;
  }

  sheet.getRange(nowSingingInfo.row, STATUS_COLUMN).setValue('Done');

  if (upNextInfo) {
    sheet.getRange(upNextInfo.row, STATUS_COLUMN).setValue('Now Singing');
  }

  const nextSingerInfo = findNextInQueue(data);
  if (nextSingerInfo) {
    sheet.getRange(nextSingerInfo.row, STATUS_COLUMN).setValue('Up Next');
  } else if (!upNextInfo) {
    ui.alert('End of Queue', 'There are no more singers waiting!', ui.ButtonSet.OK);
  }
}

/**
 * Main function for the "Skip" button. Swaps the "Now Singing" and "Up Next" singers
 * and adds a timestamped note to the skipped singer's row.
 */
function skipForNow() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const ui = SpreadsheetApp.getUi();
  const data = sheet.getDataRange().getValues();

  const nowSingingInfo = findRowByStatus(data, "Now Singing");
  const upNextInfo = findRowByStatus(data, "Up Next");

  if (!nowSingingInfo || !upNextInfo) {
    ui.alert('Action Failed', 'You need both a "Now Singing" and an "Up Next" singer to perform a skip.', ui.ButtonSet.OK);
    return;
  }
  
  const timeZone = Session.getScriptTimeZone();
  const formattedTime = Utilities.formatDate(new Date(), timeZone, "h:mm a");
  const skipNote = `Skipped at ${formattedTime}`;

  const notesCell = sheet.getRange(nowSingingInfo.row, NOTES_COLUMN);
  const existingNotes = notesCell.getValue();
  
  const newNote = existingNotes ? `${existingNotes}; ${skipNote}` : skipNote;
  notesCell.setValue(newNote);

  sheet.getRange(nowSingingInfo.row, STATUS_COLUMN).setValue('Up Next');
  sheet.getRange(upNextInfo.row, STATUS_COLUMN).setValue('Now Singing');
}

/**
 * Adds a new, blank row to the bottom of the singer list.
 */
function addNewRow() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  sheet.appendRow(['', '', '', '', '', '']);
  const lastRow = sheet.getLastRow();
  sheet.getRange(lastRow, 1).activate();
}

/**
 * Sorts the sheet by Round, then by Timestamp.
 */
function sortSheet() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  const range = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  range.sort([
    {column: ROUND_COLUMN, ascending: true},
    {column: TIMESTAMP_COLUMN, ascending: true}
  ]);
   SpreadsheetApp.flush();
}

/**
 * Sorts the sheet and sets the first two singers to "Now Singing" and "Up Next".
 */
function startShow() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const ui = SpreadsheetApp.getUi();
  sortSheet();
  
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) {
    ui.alert('Not Enough Singers', 'You need at least two singers in the queue to start the show.', ui.ButtonSet.OK);
    return;
  }
  
  sheet.getRange(2, STATUS_COLUMN).setValue('Now Singing');
  sheet.getRange(3, STATUS_COLUMN).setValue('Up Next');
}

// --- HELPER FUNCTIONS ---
function findRowByStatus(data, status) {
  for (let i = 1; i < data.length; i++) {
    if (data[i][STATUS_COLUMN - 1] === status) {
      return { row: i + 1, data: data[i] };
    }
  }
  return null;
}

function findNextInQueue(data) {
  const waitingSingers = [];
  for (let i = 1; i < data.length; i++) {
    if (data[i][STATUS_COLUMN - 1] === 'Waiting') {
      waitingSingers.push({ row: i + 1, data: data[i] });
    }
  }
  if (waitingSingers.length === 0) return null;
  waitingSingers.sort((a, b) => {
    const roundA = a.data[ROUND_COLUMN - 1];
    const roundB = b.data[ROUND_COLUMN - 1];
    if (roundA < roundB) return -1;
    if (roundA > roundB) return 1;
    const timeA = new Date(a.data[TIMESTAMP_COLUMN - 1]).getTime();
    const timeB = new Date(b.data[TIMESTAMP_COLUMN - 1]).getTime();
    return timeA - timeB;
  });
  return waitingSingers[0];
}