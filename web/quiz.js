// "Spot the red flag" quiz (spec 007). Ten situations drawn from real
// ramp-and-dump patterns; instant explanations; nothing is sent anywhere.

export const QUESTIONS = [
  { q: "A stranger texts you \"by mistake\", apologises, and invites you to a free stock-picking group on WhatsApp.", red: true,
    why: "\"Accidental\" messages that turn into an investment-club invite are how most ramp-and-dump schemes start (FBI, 2025)." },
  { q: "The group's \"professor\" shares free picks every day and asks nothing in return.", red: true,
    why: "Nothing is free: the people running the group profit when members buy the stock they already own." },
  { q: "You are told to buy a $2 stock at exactly 10:30 tomorrow, \"before the institutions\".", red: true,
    why: "Being told exactly when to buy, never when to sell, is the signature of a coordinated pump." },
  { q: "The stock has risen 150% in five days on volume ten times its normal.", red: true,
    why: "A huge run-up on abnormal volume is the price pattern this site's Layer 1 check calls a pump profile." },
  { q: "The company is a recent foreign listing with about 3 million shares trading, and hasn't filed with the SEC for months.", red: true,
    why: "Tiny float plus long filing silence makes a stock easy to move and hard to check — both FINRA red flags." },
  { q: "Group members post screenshots of huge gains after every pick.", red: true,
    why: "Screenshots are trivial to fake, and many members in these groups are bots or accomplices." },
  { q: "After you lost money, a \"recovery agent\" offers to get it back for an upfront fee.", red: true,
    why: "Recovery scams target people who already lost money. Reporting to the SEC, FINRA or the FBI is free." },
  { q: "A friend you know well mentions a large, profitable company they've owned for years and suggests you read its annual report.", red: false,
    why: "Not a pump pattern: no urgency, a large established company, and an invitation to do your own research. Still your decision." },
  { q: "You look up the adviser on FINRA BrokerCheck and find no record of them.", red: true,
    why: "Anyone giving investment advice for a living should be registered. No record is a strong warning sign." },
  { q: "Before buying, you check the ticker here, read its SEC filings and decide to wait a week.", red: false,
    why: "That's the habit that protects you: real opportunities survive a week of research; pumps don't." },
];

const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function score(answers) {
  return QUESTIONS.reduce((n, item, i) => n + (answers[i] === item.red ? 1 : 0), 0);
}

export function viewQuiz(main) {
  const answers = [];
  let i = 0;
  const draw = () => {
    if (i >= QUESTIONS.length) {
      const s = score(answers);
      const share = `${location.origin}${location.pathname}#/quiz`;
      main.innerHTML = `<div class="card"><h1>You spotted ${s} of ${QUESTIONS.length}</h1>
        <p>${s >= 9 ? "Excellent — you'd be hard to fool. Share this with someone who isn't." : s >= 6 ? "Good instincts. The ones you missed are exactly how people get caught." : "These schemes are built to look normal. Read a few real stories — they make the pattern obvious."}</p>
        <p><a class="btn" href="#/stories">Read real stories →</a> <a class="btn" href="#/help">Red flags and what to do →</a></p>
        <p class="small">Challenge a friend: <input class="share-in" readonly value="${esc(share)}" aria-label="Quiz link"></p></div>`;
      return;
    }
    const item = QUESTIONS[i];
    main.innerHTML = `<h1>Spot the red flag</h1><p class="lead">Question ${i + 1} of ${QUESTIONS.length}. Is this a warning sign?</p>
      <div class="card quiz"><p class="quiz-q">${esc(item.q)}</p>
        <div class="actions"><button class="primary" data-a="1">🚩 Red flag</button><button data-a="0">✅ Seems OK</button></div>
        <div id="why" role="status"></div></div>
      <div class="progress" aria-hidden="true"><span style="width:${(i / QUESTIONS.length) * 100}%"></span></div>`;
    main.querySelector(".actions").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-a]");
      if (!b || answers.length > i) return;
      const a = b.dataset.a === "1";
      answers.push(a);
      const right = a === item.red;
      main.querySelector("#why").innerHTML = `<p><b>${right ? "Right." : "Not quite."}</b> ${esc(item.why)}</p><button class="primary" id="next">${i + 1 < QUESTIONS.length ? "Next →" : "See my score"}</button>`;
      main.querySelectorAll("button[data-a]").forEach((x) => (x.disabled = true));
      main.querySelector("#next").addEventListener("click", () => { i += 1; draw(); });
      main.querySelector("#next").focus();
    });
  };
  draw();
}
