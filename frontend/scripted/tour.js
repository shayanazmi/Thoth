// The screenplay. Pure data: chapters of steps the director plays (director.js documents the step shape).
//   caption / sub    what the viewer reads ({hunch}, {hypothesis}… come from branches.json)
//   target           what the camera frames
//   do               what the director does in Scripted mode (and in Live with ?autopilot, except gate steps)
//   gate             an approval: in Live it always waits for the viewer's own click
//   beat             a "Your turn" moment: the viewer does it; Show me does it for them
//   until            the state that must be true before moving on
//   when             skip the step unless this holds (the run decides, e.g. whether an idea card appeared)
const idle = (a) => !a.state.busy;
const last = (a) => a.d?.messages?.[a.d.messages.length - 1];
// Layout modes exist on wide screens only.
const wideLayout = (a) => !!a.$('#layoutSeg')?.getClientRects().length;
const replied = (a) => idle(a) && a.d && ['thoth', 'thinker'].includes(last(a)?.role);

export const CHAPTERS = [
  {
    id: 'prologue', numeral: 'Prologue', title: 'A stray thought', length: '20 s',
    promise: "Every project starts as a hunch you can't quite let go of.",
    steps: [
      { caption: 'It starts on the home screen, with whatever is on your mind.', target: '#homeInput', do: ['type', '#homeInput', '{hunch}'], hold: 700 },
      { caption: 'No forms, no modes. Just say it.', sub: 'Press Enter, or the arrow.', target: '#homeForm', do: ['send', '#homeForm'],
        until: (a) => !!a.d && a.d.messages.length > 0, hold: 300 },
      { caption: 'Thoth answers like a colleague would: what is known, and where it is only guessing.', target: '#messages', until: replied, timeout: 120000,
        hotspots: [{ sel: '.unchecked', text: 'Dotted underline: general knowledge, not yet checked against sources.' }], hold: 4200 },
    ],
  },
  {
    id: 'converse', numeral: 'I', title: 'Thinking out loud', length: '30 s',
    promise: 'Conversation first. Nothing heavy runs on its own.',
    steps: [
      { caption: 'Keep thinking out loud. Thoth listens for a direction worth keeping.', target: '#composer', do: [['type', '#input', '{followup}'], ['send', '#composer']],
        until: replied, timeout: 120000, hold: 3200 },
      { when: (a) => !!a.$('.msg [data-act="promote"]'), caption: 'It noticed an idea, and asks before saving it.', target: (a) => a.$('.msg [data-act="promote"]')?.closest('.card'),
        beat: { ask: 'Keep this idea: press Save it.', target: '.msg [data-act="promote"]', done: (a) => a.d.ideas.some((i) => i.status === 'promoted') },
        do: ['click', '.msg [data-act="promote"]'], until: (a) => idle(a) && a.d.ideas.some((i) => i.status === 'promoted'), hold: 2400,
        hotspots: [{ sel: '.msg [data-act="promote"]', text: 'Ideas enter your project only when you say so.' }] },
    ],
  },
  {
    id: 'thinkers', numeral: 'II', title: 'The thinkers', length: '40 s',
    promise: 'Ten minds from the history of ideas, each with their own objections.',
    steps: [
      { caption: 'Type / to call a thinker by name, or the whole council.', target: '#composer', do: ['type', '#input', '/council'], hold: 1600,
        hotspots: [{ sel: '#slashMenu', text: 'Every action lives behind /. No modes to switch.' }] },
      { caption: 'Each thinker answers on their own, without seeing the others.', target: '#composer', do: ['send', '#composer'],
        until: (a) => idle(a) && !!a.d.council, timeout: 180000, hold: 600 },
      { caption: 'Disagreement is the point. Nobody gets a veto.', target: '#workspace', hold: 5200 },
    ],
  },
  {
    id: 'hypothesis', numeral: 'III', title: 'One hypothesis', length: '30 s',
    promise: 'Pin one clear claim. Everything after this weighs it.',
    steps: [
      { caption: 'Pin one testable claim as the working hypothesis.', target: '#composer', do: [['type', '#input', '/hypothesis {hypothesis}'], ['send', '#composer']],
        until: (a) => a.d.hypothesis.versions.length >= 1, hold: 2600 },
      { caption: 'Sharpen it. Every edit is kept as a version.', target: '#hypothesisCard',
        beat: { ask: 'Click Edit on the hypothesis and tighten the wording, or press Show me.', target: '#hypothesisCard', done: (a) => a.d.hypothesis.versions.length >= 2 },
        do: ['call', editHypothesis], until: (a) => a.d.hypothesis.versions.length >= 2, hold: 2600 },
    ],
  },
  {
    id: 'gate', numeral: 'IV', title: 'The approval gate', length: '30 s',
    promise: 'Before anything costly runs, you see exactly what will happen.',
    steps: [
      { caption: 'Put the hypothesis on trial.', target: '[data-act="stage"][data-arg="check"]', do: ['click', '[data-act="stage"][data-arg="check"]'],
        until: (a) => idle(a) && Object.keys(a.d.trialPlans || {}).length > 0, timeout: 120000, hold: 600 },
      { caption: 'It is split into the claims it is made of. You can edit each one.', target: '.trial-plan', hold: 4200,
        hotspots: [{ sel: '.trial-plan .effort', text: 'The cost, up front: papers, time, model calls.' }] },
      { caption: 'Nothing runs until you approve it.', target: '.trial-plan [data-act="runTrial"]', gate: true,
        beat: { ask: 'Press Approve and run.', target: '.trial-plan [data-act="runTrial"]', done: (a) => !!a.d.trial },
        do: ['click', '.trial-plan [data-act="runTrial"]'], until: (a) => !!a.d.trial, live: 'Press Approve and run when you are ready.', hold: 1200 },
    ],
  },
  {
    id: 'trial', numeral: 'V', title: 'The trial', length: '50 s',
    promise: 'Every paper is a witness. The court is neutral.',
    // The trial stream starts with the approval at the end of IV; jumping here replays that click first.
    jumpFrom: {
      chapter: 4,
      prepare: (d) => { const id = d.trial?.trial_id; if (id && d.trialPlans?.[id]) d.trialPlans[id].status = 'planned'; d.trial = null; },
      do: ['click', '.trial-plan [data-act="runTrial"]'], until: (a) => !!a.d?.trial,
    },
    steps: [
      { caption: 'Papers arrive as witnesses; each is read against each claim.', target: '#workspace',
        until: (a) => (a.d.trial?.order?.length || 0) >= 3, timeout: 300000, hold: 2400 },
      { caption: "And the conversation never blocks. Ask anything while it works.", target: '#composer', do: [['type', '#input', '{aside}'], ['send', '#composer']],
        until: (a) => last(a)?.role === 'thoth' || !!a.d.trial?.verdict, timeout: 120000, hold: 2600 },
      { caption: 'Weighing every witness…', target: '#workspace', until: (a) => !!a.d.trial?.verdict, timeout: 1800000, hold: 400 },
      { caption: 'The ruling.', sub: 'Including what it could not read in full.', target: '.ruling', hold: 6400,
        hotspots: [{ sel: '.ruling .facts', text: 'Full text vs abstract only: an abstract is never passed off as the paper.' }, { sel: '.ruling .scale', text: 'Five honest outcomes, from contradicted to already established.' }] },
    ],
    quiz: 'abstract',
  },
  {
    id: 'review', numeral: 'VI', title: 'What is already known', length: '45 s',
    promise: 'A systematic review: protocol first, then every screening decision on the record.',
    steps: [
      { caption: 'For the full picture, plan a systematic review.', target: '#composer', do: [['type', '#input', '/review'], ['send', '#composer']],
        until: (a) => idle(a) && Object.keys(a.d.reviewPlans || {}).length > 0, timeout: 180000, hold: 600 },
      { caption: 'The protocol: who, what, which designs. Screen on what was studied, never on what was found.', target: '.review-protocol', hold: 4600 },
      { caption: 'Auto mode screens for you; uncertain records are flagged, not guessed.', target: '.review-protocol .mode-switch', do: ['click', '.review-protocol input[value="auto"]'], hold: 1600 },
      { caption: 'Approve, and it runs.', target: '.review-protocol [data-act="runReview"]', gate: true,
        beat: { ask: 'Press Approve and run.', target: '.review-protocol [data-act="runReview"]', done: (a) => !!a.d.sysReview },
        do: ['click', '.review-protocol [data-act="runReview"]'], until: (a) => !!a.d.sysReview, live: 'Choose a mode, then press Approve and run.', hold: 800 },
      { caption: 'Searching, screening, retrieving full texts. Every count comes from a recorded decision.', target: '#workspace',
        until: (a) => ['complete', 'blocked', 'awaiting_researcher'].includes(a.d.sysReview?.status), timeout: 2400000, hold: 6000 },
    ],
  },
  {
    id: 'design', numeral: 'VII', title: 'Designing the study', length: '40 s',
    promise: 'A study you can actually run, with the time and people you have.',
    steps: [
      { caption: 'Tell Thoth what you have to work with.', target: '[data-act="stage"][data-arg="design"]', do: ['click', '[data-act="stage"][data-arg="design"]'], hold: 1200 },
      { caption: 'Time, access, budget, skills. Designs are fitted to them.', target: 'form[data-form="resources"]', do: ['call', fillResources], hold: 800 },
      { caption: 'Candidate designs, each with what it can and cannot conclude.', target: 'form[data-form="resources"]', do: ['send', 'form[data-form="resources"]'],
        until: (a) => idle(a) && !!a.d.design?.candidates?.designs?.length, timeout: 300000, hold: 4200 },
      { caption: 'Choose one. It becomes the Design section of your research file.', target: '[data-act="chooseDesign"]',
        beat: { ask: 'Pick a design (Choose), then confirm.', target: '[data-act="chooseDesign"]', done: (a) => !!a.d.design?.chosen },
        do: [['click', '[data-act="chooseDesign"]'], ['dialog', '']], until: (a) => !!a.d.design?.chosen, timeout: 120000, hold: 3000 },
    ],
  },
  {
    id: 'draft', numeral: 'VIII', title: 'The draft', length: '50 s',
    promise: 'Written from your evidence, and honest about what is still open.',
    steps: [
      { caption: 'Draft a research proposal from everything in the file.', target: '[data-act="stage"][data-arg="draft"]', do: [['click', '[data-act="stage"][data-arg="draft"]'], ['click', '[data-act="startProposal"]']],
        until: (a) => idle(a) && !!a.d.proposal?.has_outline, timeout: 300000, hold: 600 },
      { caption: 'An outline first. You can reorder, add or drop sections.', target: '#workspace', hold: 3600 },
      { caption: 'Approve the outline and each section is written, then checked claim by claim.', target: '[data-act="proposalApprove"]', gate: true,
        beat: { ask: 'Approve the outline.', target: '[data-act="proposalApprove"]', done: (a) => !!a.d.proposal?.approved },
        do: ['click', '[data-act="proposalApprove"]'], until: (a) => !!a.d.proposal?.approved, live: 'Approve the outline when it looks right.', hold: 600 },
      { caption: 'Writing, verifying, then a peer reviewer reads the whole thing.', target: '#workspace', until: (a) => idle(a) && (a.d.proposal?.status?.sections_written || 0) > 0, timeout: 2400000, hold: 2400 },
      { caption: 'Provisional until every gap is closed. Never falsely complete.', target: '.pz-status', hold: 5200,
        hotspots: [{ sel: '.pz-status .pz-meters', text: 'Verifier, reviewer and thinkers: what was checked, removed and still open.' }] },
      { caption: 'Even exporting asks first, and a provisional draft is watermarked.', target: '[data-act="pzExport"]', do: [['click', '[data-act="pzExport"]'], ['wait', 2600], ['dialog', null, 'cancel']], hold: 1200 },
    ],
    quiz: 'provisional',
  },
  {
    id: 'howto', numeral: 'IX', title: 'Your turn', length: '30 s',
    promise: 'Everything you need, in thirty seconds.', card: true,
    steps: [
      { caption: 'Type / for every action: thinkers, checks, reviews, drafts.', target: '#composer', do: ['type', '#input', '/'], hold: 2600 },
      { when: wideLayout, caption: 'Give the research file the whole screen…', target: '#layoutSeg', do: [['call', (a) => { a.$('#input').value = ''; a.$('#input').dispatchEvent(new Event('input')); }], ['click', '#layoutSeg [data-layout="file"]']], hold: 2200 },
      { when: wideLayout, caption: '…or just the conversation.', target: '#layoutSeg', do: ['click', '#layoutSeg [data-layout="chat"]'], hold: 1800 },
      { caption: 'Night or papyrus. Your choice.', target: '#themeToggle', beat: { ask: 'Switch the theme.', target: '#themeToggle', done: themeFlipped, skipDoes: false },
        do: ['click', '#themeToggle'], hold: 1600 },
      { caption: 'Your projects live in the sidebar, each with its moon.', target: '#sidebar', do: ['call', (a) => { if (wideLayout(a)) a.$('#layoutSeg [data-layout="split"]').click(); }], hold: 2600 },
    ],
  },
];

// Hypothesis edit, as a person would: Edit → retype → Enter.
async function editHypothesis(a) {
  a.$('[data-act="hypEdit"]')?.click();
  await new Promise((r) => setTimeout(r, 400));
  const el = a.$('#hypText');
  if (!el) return;
  el.textContent = '';
  for (const ch of a.branch.refined) { el.textContent += ch; await new Promise((r) => setTimeout(r, 18)); }
  // A background tab never focuses the field, so blur would not fire on its own; finish the edit explicitly.
  el.dispatchEvent(new Event('blur'));
}

async function fillResources(a) {
  const form = a.$('form[data-form="resources"]');
  if (!form) return;
  for (const [k, v] of Object.entries(a.branch.resources || {})) {
    const f = form[k];
    if (!f) continue;
    f.value = '';
    for (const ch of v) { f.value += ch; await new Promise((r) => setTimeout(r, 14)); }
  }
}

let theme0 = null;
function themeFlipped() {
  const t = document.documentElement.dataset.theme || 'dark';
  if (theme0 === null) theme0 = t;
  return t !== theme0;
}

export const REELS = [
  { id: 'gate', title: 'The approval gate in 40 seconds', length: '40 s', chapters: [4] },
  { id: 'thinkers', title: 'Working with thinkers in a minute', length: '60 s', chapters: [2, 3] },
  { id: 'trial', title: 'Hunch to ruling', length: '90 s', chapters: [0, 4, 5] },
  { id: 'draft', title: 'From draft to export', length: '50 s', chapters: [8] },
  { id: 'howto', title: 'Keyboard and layout tricks', length: '30 s', chapters: [9] },
];

export const GLOSSARY = [
  ['Hunch', 'Anything on your mind. Thoth helps turn it into a question worth asking.'],
  ['Idea card', 'A direction Thoth noticed in the conversation. Saved only if you say so.'],
  ['Thinker council', 'Historical thinkers who each answer on their own; disagreement is shown, nobody has a veto.'],
  ['Hypothesis', 'The one claim the project weighs. Every edit is kept as a version.'],
  ['Approval gate', 'Anything costly shows its plan and cost first, and runs only on your click.'],
  ['Trial', 'Your hypothesis split into claims; each paper is a witness read against each claim.'],
  ['Full text / abstract only', 'How much of a paper was actually read. Never upgraded, never hidden.'],
  ['Ruling', "The neutral court's verdict, from contradicted to already established, with its gaps."],
  ['Systematic review', 'Protocol, search, screening and inclusion, with PRISMA counts from recorded decisions.'],
  ['Study design', 'Candidate designs fitted to your time, access and skills, each with what it can conclude.'],
  ['Provisional', 'A draft with open gaps. It is never labelled complete until they are closed.'],
];

export const QUIZ = {
  abstract: { q: 'Thoth could read only the abstracts of six papers. How does the ruling treat them?', options: ['As full papers', 'Labelled abstract only, and weighed with that limit', 'They are hidden'], answer: 1,
    why: 'Abstract-level reading is never presented as full-text analysis. The ruling says how many witnesses were read in full.' },
  provisional: { q: 'The reviewer left one major concern open. Can the proposal be labelled complete?', options: ['Yes, it is written', 'No: it stays provisional and lists the gap'], answer: 1,
    why: 'A report with unresolved critical evidence or review is provisional, with the gaps listed. Exports are watermarked.' },
};
