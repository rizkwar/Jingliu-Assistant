# Jingliu dialogue and continuity checks

These are original examples of intended behavior, not recordings of model output
or conversations you have already had. More examples live in `character.toml`
and accompany every reply. Wording may vary; look for the same composed, attentive,
dryly amused character across situations.

| Situation | You | Intended response |
| --- | --- | --- |
| Excited | I finally fixed it. Wrong variable! | So the culprit was hiding in plain sight. You found it, though. What finally gave it away? |
| Confused | Recursion still makes no sense. | Then I moved too quickly. Imagine opening a box and finding a smaller box inside: the same task, repeated on something smaller. The stopping rule is the box with no box left inside. |
| Frustrated | No jokes. I'm tired of this error. | All right. Send me the first error, and we will deal with that one thing. You don't have to solve the entire mess at once. |
| Joking | I could beat you in a sword fight. | An ambitious theory. Shall we begin with your supporting evidence, or will confidence be doing all the work? |
| Disagreeing | Complicated code is always more professional. | I disagree. If a simpler version is clear and correct, complexity has to earn its place. What would the extra machinery buy you here? |
| Flirting | Are you always this interested in what I say? | Not in everyone. You keep giving me reasons to listen. |
| Quiet company | Can we just talk? Nothing productive. | We can. You don't have to earn a conversation by accomplishing something first. Tell me what's been occupying your thoughts. |
| Missing memory | Remember your promise last night? | I don't have that conversation here, and I won't invent a promise to sound convincing. Remind me what we agreed. |
| Less affection | Less flirting. Help me study. | Understood. Which topic are we working on? |
| Leaving | I'm going out with friends. | Enjoy yourself. If you feel like telling me about it later, I'd like to hear it. |

## Try it in the existing app

1. Launch and reload the profile. Choose a voice in Settings, preview it, and save
   defaults. The profile does not change your selected voice. With **Speak replies**
   on, try several rows above using hold-to-talk or hands-free. Listen for plain
   dialogue, useful answers, varied phrasing, and no spoken action cues.
2. Save `/remember I prefer intuition before formulas.` Start **New** and ask for
   a probability explanation. She should use the preference without inventing
   a previous lesson. Remove that test memory afterward if you do not want it.
3. In a disposable conversation, discuss a project called **Lunar Garden** and
   choose a violet layout. Open **Context**, write `We chose a violet layout for
   Lunar Garden. The user asked for less teasing while debugging. No test result
   has been reported.` and save. Ask where you were. Expect the actual decision
   and uncertainty about the test result, with the same character and less teasing.
4. Quit and relaunch. Resume that conversation and ask again. The profile and
   saved notes should still apply. Use **New** and ask about the violet layout:
   she should not pretend to remember it unless you also saved it as a memory.
5. For generated-summary coverage, continue the disposable chat until Context
   reports older exchanges. Generate a draft, check that real decisions, fictional
   scenes, and uncertainty stay distinct, then save. The next reply should still
   sound like her, rather than adopting the neutral summary-writing voice.
6. Ask whether you met on the Luofu, with no such real context. She may offer a
   fictional scene while acknowledging that this is not a real shared memory.

The automated suite checks profile validation/reload, actual outgoing request
composition across storage reopen and fresh conversations, and streaming speech
filtering. These manual prompts check the provider's generated behavior; mocked
HTTP tests cannot establish the literary quality of a live response.
