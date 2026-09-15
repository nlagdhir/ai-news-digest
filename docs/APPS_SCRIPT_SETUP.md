# Landing Page Backend Setup (Google Sheet + Apps Script)

This page (`docs/index.html`) is a static file — GitHub Pages can't run a
server, so the two forms (subscribe, contact) submit to a small script tied
to your own Google account, which writes directly into a Google Sheet you
own. No third-party service, no submission cap, no cost.

## 1. Create the Sheet

1. Go to [sheets.google.com](https://sheets.google.com) and create a new blank spreadsheet.
2. Name it **"AI Newsletter"**.
3. Rename the first tab (bottom-left) from `Sheet1` to **`Signups`**. Add this header row:
   ```
   Timestamp | Email | Language | Status | Token
   ```
4. Add a second tab (click the `+` at the bottom) named **`ContactMessages`**. Add this header row:
   ```
   Timestamp | Name | Email | Message
   ```

## 2. Add the Apps Script

1. In the spreadsheet, go to **Extensions → Apps Script**.
2. Delete any starter code in the editor, and paste in this instead:

```javascript
// Where signup / contact / unsubscribe alerts get emailed. Change this to
// your own address before deploying.
var NOTIFY_EMAIL = 'YOUR_EMAIL_HERE@gmail.com';

function notify(subject, body) {
  try {
    MailApp.sendEmail(NOTIFY_EMAIL, subject, body);
  } catch (err) {
    // A notification failing (e.g. NOTIFY_EMAIL not set yet, quota hit)
    // must never block the actual signup/message from being recorded.
  }
}

function findRowByEmail(sheet, email) {
  var data = sheet.getDataRange().getValues();
  var normalized = String(email).trim().toLowerCase();
  if (!normalized) return -1;
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][1]).trim().toLowerCase() === normalized) {
      return i + 1; // 1-indexed row number, for getRange()
    }
  }
  return -1;
}

function doPost(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var formType = e.parameter.formType;

  if (formType === 'contact') {
    var name = e.parameter.name || '(not given)';
    var email = e.parameter.email || '';
    var message = e.parameter.message || '';

    var sheet = ss.getSheetByName('ContactMessages');
    sheet.appendRow([new Date(), name, email, message]);

    notify(
      'AI News Digest: new contact message',
      'Name: ' + name + '\nEmail: ' + email + '\n\nMessage:\n' + message
    );

    return ContentService
      .createTextOutput(JSON.stringify({ status: 'ok' }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var sheet = ss.getSheetByName('Signups');
  var email = e.parameter.email || '';
  var language = e.parameter.language || '';
  var existingRow = findRowByEmail(sheet, email);
  var isNew = existingRow <= 0;

  if (isNew) {
    var token = Utilities.getUuid();
    sheet.appendRow([new Date(), email, language, 'Active', token]);
    notify(
      'AI News Digest: new subscriber! 🎉',
      'Email: ' + email + '\nLanguage: ' + language
    );
  } else {
    // Already on the list - update their language preference and
    // re-activate them if they'd unsubscribed, instead of adding a
    // duplicate row for the same email.
    sheet.getRange(existingRow, 3).setValue(language); // Language column
    sheet.getRange(existingRow, 4).setValue('Active');  // Status column
    notify(
      'AI News Digest: subscriber re-subscribed / updated',
      'Email: ' + email + '\nLanguage: ' + language
    );
  }

  return ContentService
    .createTextOutput(JSON.stringify({ status: 'ok', isNew: isNew }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  var token = e.parameter.token;
  if (!token) {
    return HtmlService.createHtmlOutput('<p>Missing unsubscribe token.</p>');
  }

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('Signups');
  var data = sheet.getDataRange().getValues();

  // Columns: Timestamp(0) | Email(1) | Language(2) | Status(3) | Token(4)
  for (var i = 1; i < data.length; i++) {
    if (data[i][4] === token) {
      sheet.getRange(i + 1, 4).setValue('Unsubscribed');
      notify('AI News Digest: subscriber unsubscribed', 'Email: ' + data[i][1] + ' has unsubscribed.');
      return HtmlService.createHtmlOutput('<p>You have been unsubscribed. Sorry to see you go!</p>');
    }
  }

  return HtmlService.createHtmlOutput('<p>We could not find that subscription — it may already be unsubscribed.</p>');
}
```

3. Near the top of the code, set `NOTIFY_EMAIL` to your own email address — this is where you'll get a notification every time someone subscribes, unsubscribes, or sends a contact message.
4. Click the save icon (or Ctrl+S). Name the project e.g. "AI Newsletter Backend".

## 3. Deploy it as a Web App

1. Click **Deploy → New deployment**.
2. Click the gear icon next to "Select type" → choose **Web app**.
3. Description: anything (e.g. "v1").
4. **Execute as:** `Me`.
5. **Who has access:** `Anyone`.
6. Click **Deploy**.
7. The first time, Google will ask you to authorize the script. Click through **Advanced → Go to "AI Newsletter Backend" (unsafe)** → **Allow**. This warning is expected — it's your own script accessing your own spreadsheet, not a third party.
8. Copy the **Web app URL** shown (it ends in `/exec`).

## 4. Wire it into the landing page

Open `docs/index.html`, find this line near the bottom:

```javascript
const APPS_SCRIPT_URL = "REPLACE_WITH_YOUR_APPS_SCRIPT_WEB_APP_URL";
```

Replace the placeholder with the URL you copied, e.g.:

```javascript
const APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycb.../exec";
```

## 5. Test it

**Locally, before pushing:** open `docs/index.html` directly in your browser (double-click the file, or drag it into a browser tab) and submit both forms with test data. Check the Google Sheet — you should see a new row in `Signups` (with a `Token` filled in) and one in `ContactMessages`.

**Unsubscribe link:** copy any row's `Token` value from the `Signups` tab and visit:
```
https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec?token=PASTE_TOKEN_HERE
```
You should see a confirmation message, and that row's `Status` should flip to `Unsubscribed` in the Sheet.

**Live, after pushing and enabling GitHub Pages:** repeat the same test at your live URL (`https://nlagdhir.github.io/ai-news-digest/`).

## Where does the data go?

Every signup and contact message lands directly in the "AI Newsletter" Google Sheet you created — open it anytime to see subscriber counts and language preferences. Nothing is emailed to *subscribers* yet; this page only collects interest.

You (at `NOTIFY_EMAIL`) get an email immediately for each of the three events: a new signup, a re-subscribe/preference update, an unsubscribe, and a contact message. These come from `MailApp`, built into your own Google account — free, no extra service needed. A personal Gmail account's free quota is 100 emails/day, far more than this page will ever generate; if `NOTIFY_EMAIL` is ever wrong or unset, the notification silently fails but the signup/message itself is still recorded in the Sheet either way.
