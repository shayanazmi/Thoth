/**
 * Thoth · Client Application Engine
 * High-performance SSE stream handler, SVG Knowledge Graph, Vault Explorer & REPL
 */

class ThothApp {
  constructor() {
    this.currentView = 'landing'; // 'landing' | 'studio'
    this.activeTopic = '';
    this.activeMode = 'auto'; // 'auto' | 'deep_research' | 'web_probe' | 'local_qa' | 'expand_report' | 'fast_chat'
    this.currentState = null;
    this.chatTurns = [];
    this.vaultNotes = [];
    this.activeArtifactTab = 'report';
    this.isGenerating = false;
    this.eventSource = null;

    this.pipelineNodes = ['search', 'snowball', 'scrape', 'writer', 'verifier', 'critic', 'mindmap', 'vault'];
    this.pipelineLabels = {
      search: 'Searcher',
      snowball: 'Snowballer',
      scrape: 'Reader',
      writer: 'Scribe',
      verifier: 'Truth Guard',
      critic: 'Critic',
      mindmap: 'Mind Map',
      vault: 'Vault Indexer'
    };

    this.modeLabels = {
      fast_chat: { label: 'Chat', icon: 'message-square' },
      deep_research: { label: 'Deep Research', icon: 'microscope' },
      web_probe: { label: 'Web Probe', icon: 'globe' },
      local_qa: { label: 'Vault QA', icon: 'book-marked' },
      expand_report: { label: 'Expand Report', icon: 'file-plus' },
      auto: { label: 'Auto Router', icon: 'sparkles' }
    };
    // Default mode is fast_chat — research is opt-in
    this.activeMode = 'fast_chat';

    this.initElements();
    this.bindEvents();
    this.setMode('fast_chat'); // Initialize UI to default chat mode
    this.loadVaultNotes();
  }

  initElements() {
    // Views
    this.landingView = document.getElementById('landingView');
    this.studioView = document.getElementById('studioView');
    this.tabLandingBtn = document.getElementById('tabLandingBtn');
    this.tabStudioBtn = document.getElementById('tabStudioBtn');

    // Inputs & Buttons
    this.heroPromptInput = document.getElementById('heroPromptInput');
    this.heroLaunchBtn = document.getElementById('heroLaunchBtn');
    this.chatInput = document.getElementById('chatInput');
    this.chatSendBtn = document.getElementById('chatSendBtn');

    // Floating Tool Menu & Mode Pills
    this.toolAttachBtn = document.getElementById('toolAttachBtn');
    this.floatingToolMenu = document.getElementById('floatingToolMenu');
    this.activeModeBadge = document.getElementById('activeModeBadge');
    this.activeModeLabel = document.getElementById('activeModeLabel');
    this.deepResearchToggle = document.getElementById('deepResearchToggle');

    // Feeds & Containers
    this.chatFeed = document.getElementById('chatFeed');
    this.stepperBar = document.getElementById('pipelineStepperBar');
    this.currentTopicDisplay = document.getElementById('currentTopicDisplay');
    this.vaultNotesList = document.getElementById('vaultNotesList');
    this.vaultSearchInput = document.getElementById('vaultSearchInput');

    // Artifact Panes
    this.artifactReportPane = document.getElementById('artifactReportPane');
    this.artifactTruthPane = document.getElementById('artifactTruthPane');
    this.artifactMindmapPane = document.getElementById('artifactMindmapPane');
    this.artifactSourcesPane = document.getElementById('artifactSourcesPane');

    // Modal
    this.noteModal = document.getElementById('noteModal');
    this.modalTitle = document.getElementById('modalTitle');
    this.modalBody = document.getElementById('modalBody');
    this.modalCloseBtn = document.getElementById('modalCloseBtn');
  }

  bindEvents() {
    // 3D Parallax
    if (window.ThothAnimations) {
      window.ThothAnimations.init3DParallax();
    }

    // View Switching
    this.tabLandingBtn?.addEventListener('click', () => this.switchView('landing'));
    this.tabStudioBtn?.addEventListener('click', () => this.switchView('studio'));

    // Hero Launcher
    this.heroLaunchBtn?.addEventListener('click', () => this.handleHeroLaunch());
    this.heroPromptInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.handleHeroLaunch();
    });

    // Preset chips
    document.querySelectorAll('.preset-chip').forEach(chip => {
      chip.addEventListener('click', (e) => {
        const query = e.target.getAttribute('data-query');
        if (query) {
          this.heroPromptInput.value = query;
          this.handleHeroLaunch();
        }
      });
    });

    // Chat REPL Input
    this.chatSendBtn?.addEventListener('click', () => this.handleChatSend());
    this.chatInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleChatSend();
      }
    });

    // Tool Menu Toggle
    this.toolAttachBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleToolMenu();
    });
    this.activeModeBadge?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleToolMenu();
    });

    // Close tool menu when clicking outside
    document.addEventListener('click', (e) => {
      if (this.floatingToolMenu && !this.floatingToolMenu.contains(e.target) && e.target !== this.toolAttachBtn && e.target !== this.activeModeBadge) {
        this.floatingToolMenu.classList.add('hidden');
      }
    });

    // Tool Menu Item Selection
    document.querySelectorAll('.tool-menu-item').forEach(item => {
      item.addEventListener('click', (e) => {
        const targetItem = e.currentTarget;
        const mode = targetItem.getAttribute('data-mode');
        if (mode) {
          this.setMode(mode);
          this.floatingToolMenu.classList.add('hidden');
        }
      });
    });

    // Deep Research Quick Toggle — switches between chat and research
    this.deepResearchToggle?.addEventListener('click', () => {
      if (this.activeMode === 'deep_research') {
        this.setMode('fast_chat');
      } else {
        this.setMode('deep_research');
      }
    });

    // Artifact Tab Switching
    document.querySelectorAll('.artifact-tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tab = e.target.getAttribute('data-tab');
        this.switchArtifactTab(tab);
      });
    });


    // Vault Search
    this.vaultSearchInput?.addEventListener('input', (e) => {
      this.filterVaultNotes(e.target.value);
    });

    // Modal Close
    this.modalCloseBtn?.addEventListener('click', () => {
      this.noteModal.classList.add('hidden');
    });
    this.noteModal?.addEventListener('click', (e) => {
      if (e.target === this.noteModal) this.noteModal.classList.add('hidden');
    });
  }

  switchView(viewName) {
    if (this.currentView === viewName) return;
    this.currentView = viewName;

    const fromEl = viewName === 'studio' ? this.landingView : this.studioView;
    const toEl = viewName === 'studio' ? this.studioView : this.landingView;

    if (viewName === 'studio') {
      this.tabStudioBtn?.classList.add('active');
      this.tabLandingBtn?.classList.remove('active');
    } else {
      this.tabLandingBtn?.classList.add('active');
      this.tabStudioBtn?.classList.remove('active');
    }

    if (window.ThothAnimations) {
      window.ThothAnimations.animateViewTransition(fromEl, toEl);
    } else {
      fromEl.classList.add('hidden');
      toEl.classList.remove('hidden');
    }
  }

  switchArtifactTab(tabName) {
    this.activeArtifactTab = tabName;
    document.querySelectorAll('.artifact-tab-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-tab') === tabName);
    });

    const panes = {
      report: this.artifactReportPane,
      truth: this.artifactTruthPane,
      mindmap: this.artifactMindmapPane,
      sources: this.artifactSourcesPane
    };

    Object.keys(panes).forEach(k => {
      if (panes[k]) {
        panes[k].classList.toggle('hidden', k !== tabName);
      }
    });

    if (tabName === 'mindmap' && this.currentState?.mindmap) {
      this.renderMindMap(this.currentState.mindmap);
    }
  }

  toggleToolMenu() {
    if (!this.floatingToolMenu) return;
    this.floatingToolMenu.classList.toggle('hidden');
    if (this.toolAttachBtn) {
      this.toolAttachBtn.classList.toggle('active', !this.floatingToolMenu.classList.contains('hidden'));
    }
  }

  setMode(mode) {
    this.activeMode = mode;
    const info = this.modeLabels[mode] || { label: 'Chat', icon: 'message-square' };
    const isResearch = mode === 'deep_research';

    if (this.activeModeLabel) {
      this.activeModeLabel.textContent = info.label;
    }
    if (this.activeModeBadge) {
      this.activeModeBadge.innerHTML = `<i data-lucide="${info.icon}" style="width:12px;height:12px;"></i> <span>${info.label}</span> <i data-lucide="chevron-down" style="width:10px;height:10px;opacity:0.6;"></i>`;
    }
    if (this.deepResearchToggle) {
      this.deepResearchToggle.classList.toggle('active', isResearch);
      // Update icon inside the Deep Research button to show current state
      const btnIcon = this.deepResearchToggle.querySelector('i[data-lucide]');
      if (btnIcon) btnIcon.setAttribute('data-lucide', isResearch ? 'microscope' : 'microscope');
      const btnSpan = this.deepResearchToggle.querySelector('span');
      if (btnSpan) btnSpan.textContent = isResearch ? 'Deep Research' : 'Deep Research';
    }

    // Send button icon: arrow-up for chat, zap for research
    if (this.chatSendBtn) {
      this.chatSendBtn.innerHTML = `<i data-lucide="${isResearch ? 'zap' : 'arrow-up'}" style="width:15px;height:15px;"></i>`;
      this.chatSendBtn.title = isResearch ? 'Launch Research Swarm' : 'Send Message';
      this.chatSendBtn.style.background = isResearch
        ? 'linear-gradient(135deg, hsl(32, 65%, 48%), hsl(42, 80%, 55%))'
        : '';
    }

    // Update active highlight in menu items
    document.querySelectorAll('.tool-menu-item').forEach(el => {
      el.classList.toggle('active', el.getAttribute('data-mode') === mode);
    });

    if (window.lucide) lucide.createIcons();

    // Update placeholder text
    const placeholders = {
      deep_research: 'Enter a topic to trigger the 8-agent research swarm & vault synthesis...',
      web_probe: 'Enter query for live targeted arXiv & web literature search...',
      local_qa: 'Ask a question over your indexed Obsidian notes & research report...',
      expand_report: 'Describe the section or comparison you want added to the report...',
      fast_chat: 'Ask Thoth anything — chat, explain, discuss...'
    };
    if (this.chatInput) {
      this.chatInput.placeholder = placeholders[mode] || 'Ask Thoth anything...';
    }
  }

  handleHeroLaunch() {
    const topic = this.heroPromptInput.value.trim();
    if (!topic || this.isGenerating) return;
    this.switchView('studio');

    // Route casual greetings directly to fast conversational chat
    const casualPatterns = /^(hi|hello|hey|greetings|hola|howdy|sup|test|yo)(\s+.*|\!|\?)*$/i;
    if (casualPatterns.test(topic) || topic.length < 4) {
      this.setMode('fast_chat');
      this.appendUserMessage(topic);
      this.sendFollowup(topic);
    } else {
      this.setMode('deep_research');
      this.startResearch(topic, true);
    }
  }

  handleChatSend() {
    const text = this.chatInput.value.trim();
    if (!text || this.isGenerating) return;

    this.chatInput.value = '';

    // Handle Slash Commands
    if (text.startsWith('/')) {
      this.handleSlashCommand(text);
      return;
    }

    this.appendUserMessage(text);

    // ROUTING LOGIC:
    // - fast_chat (default): ALWAYS go to direct conversational path — never trigger the swarm
    // - deep_research: ALWAYS trigger the full 8-agent swarm
    // - Other modes (web_probe, local_qa, expand_report): follow-up stream
    if (this.activeMode === 'deep_research') {
      this.startResearch(text, false);
      return;
    }

    // All non-research modes go through the fast conversational path
    this.sendFollowup(text);
  }

  handleSlashCommand(cmd) {
    const parts = cmd.split(' ');
    const command = parts[0].toLowerCase();

    if (command === '/report') {
      this.switchArtifactTab('report');
      this.appendAssistantMessage('Opened **Living Synthesis Report** in the right artifact pane.');
    } else if (command === '/mindmap') {
      this.switchArtifactTab('mindmap');
      this.appendAssistantMessage('Switched to **Concept Mind Map** graph visualizer.');
    } else if (command === '/vault' || command === '/notes') {
      this.loadVaultNotes();
      this.appendAssistantMessage('Refreshed local **Obsidian Vault** notes index.');
    } else if (command === '/truth' || command === '/scales') {
      this.switchArtifactTab('truth');
      this.appendAssistantMessage('Opened **Scales of Ma\'at** Fact Verification Audit.');
    } else if (command === '/clear' || command === '/reset') {
      this.chatFeed.innerHTML = '';
      this.currentState = null;
      this.activeTopic = '';
      this.currentTopicDisplay.textContent = 'Awaiting Objective';
      this.appendAssistantMessage('Research workspace reset. Enter a new topic to begin.');
    } else {
      this.appendAssistantMessage(`**Available Slash Commands:**\n- \`/report\` — View full synthesis report\n- \`/mindmap\` — Inspect interactive concept graph\n- \`/truth\` — View Scales of Ma'at verification results\n- \`/vault\` — Refresh Obsidian vault index\n- \`/clear\` — Reset session`);
    }
  }

  // ============================================================================
  // SSE RESEARCH STREAMING (Turn 0: Discovery)
  // ============================================================================
  startResearch(topic, shouldAppendUser = true) {
    this.activeTopic = topic;
    this.isGenerating = true;
    this.currentTopicDisplay.textContent = topic;
    if (this.stepperBar) this.stepperBar.innerHTML = '';

    if (shouldAppendUser) {
      this.appendUserMessage(topic);
    }

    // Create placeholder assistant message with active stepper and CoT accordion
    const msgId = `msg_${Date.now()}`;
    const bubbleEl = this.createAssistantPlaceholder(msgId);

    const payload = {
      topic: topic,
      mode: 'deep_research',   // startResearch is ONLY called in deep_research mode
      role: "senior academic researcher",
      tone: "formal and analytical",
      scrape_top_n: 2,
      min_score: 6.5
    };

    fetch('/api/research/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(response => {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processStream = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            this.isGenerating = false;
            this.loadVaultNotes();
            return;
          }

          buffer += decoder.decode(value, { stream: true });
          // Normalize CRLF (\r\n) to LF (\n) — sse_starlette uses HTTP CRLF line endings
          buffer = buffer.replace(/\r\n/g, '\n');
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop(); // Keep last incomplete chunk

          for (const block of blocks) {
            for (const line of block.split('\n')) {
              const trimmed = line.trim();
              if (trimmed.startsWith('data:')) {
                const jsonStr = trimmed.slice(5).trim();
                if (!jsonStr) continue;
                try {
                  const event = JSON.parse(jsonStr);
                  this.handlePipelineEvent(event, msgId);
                } catch (e) {
                  console.error('SSE Parse Error:', e, jsonStr);
                }
              }
            }
          }

          processStream();
        }).catch(err => {
          console.error('SSE Stream read error:', err);
          this.isGenerating = false;
        });
      };

      processStream();
    }).catch(err => {
      console.error('Fetch error:', err);
      this.isGenerating = false;
    });
  }

  handlePipelineEvent(event, msgId) {
    const { node, update, state } = event;
    this.currentState = state;

    const msgContainer = document.getElementById(msgId);
    if (!msgContainer) return;

    const cotBody = msgContainer.querySelector('.cot-body');
    const contentBody = msgContainer.querySelector('.message-prose');

    // Handle Fast Direct Chat Path (Greetings & Casual Q&A)
    if (node === 'direct_chat') {
      const directAnswer = update.answer || state.direct_answer || '';
      if (contentBody) {
        contentBody.innerHTML = marked.parse(directAnswer);
      }
      const cotAccordion = msgContainer.querySelector('.cot-accordion');
      if (cotAccordion) cotAccordion.style.display = 'none';
      if (state.follow_up_questions) {
        this.renderProactivePills(msgContainer, state.follow_up_questions);
      }
      return;
    }

    // Lazy initialize & update Stepper Badges only when real research nodes run
    if (this.pipelineNodes.includes(node)) {
      if (this.stepperBar && (!this.stepperBar.children || this.stepperBar.children.length === 0)) {
        this.resetStepper();
      }
      this.updateStepperNode(node);
    }

    // Update Chain of Thought logs
    if (cotBody) {
      if (node === 'search') {
        cotBody.textContent += `[SEARCH] Retrieved primary literature from Semantic Scholar & Web.\n`;
      } else if (node === 'snowball') {
        cotBody.textContent += `[SNOWBALL] Expanded citation graph and forward reference seeds.\n`;
      } else if (node === 'scrape') {
        cotBody.textContent += `[READER] Scraped readable text from candidate sources.\n`;
      } else if (node === 'writer') {
        cotBody.textContent += `[SCRIBE] Drafted synthesis report (Attempt ${state.attempt || 1}).\n`;
      } else if (node === 'verifier') {
        cotBody.textContent += `[TRUTH GUARD] Verified claims against retrieved sources.\n`;
      } else if (node === 'critic') {
        cotBody.textContent += `[CRITIC] Rubric evaluated. Score: ${state.score || 0}/10.\n`;
      } else if (node === 'vault') {
        cotBody.textContent += `[VAULT] Persisted notes to Obsidian Markdown Vault & Indexed.\n`;
      }
    }

    // Update Report & Artifacts in real-time
    if (state.report) {
      this.renderReport(state.report);
      contentBody.innerHTML = marked.parse(state.report);
    }

    if (state.verification_results) {
      this.renderTruthGuard(state.verification_results);
    }

    if (state.mindmap) {
      this.renderMindMap(state.mindmap);
    }

    if (state.cumulative_sources) {
      this.renderSources(state.cumulative_sources);
    }

    // On completion
    if (node === 'follow_up' || node === 'complete') {
      this.completeStepper();
      if (state.follow_up_questions) {
        this.renderProactivePills(msgContainer, state.follow_up_questions);
      }
    }
  }

  // ============================================================================
  // SSE FOLLOW-UP STREAMING (Multi-Turn Chat REPL)
  // ============================================================================
  sendFollowup(query) {
    if (!this.currentState) {
      this.startResearch(query);
      return;
    }

    this.isGenerating = true;
    const mode = this.activeMode || 'auto';

    const msgId = `msg_${Date.now()}`;
    const bubbleEl = this.createAssistantPlaceholder(msgId);

    const payload = {
      state: this.currentState,
      user_query: query,
      mode_override: mode
    };

    fetch('/api/followup/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(response => {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processStream = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            this.isGenerating = false;
            this.loadVaultNotes();
            return;
          }

          buffer += decoder.decode(value, { stream: true });
          // Normalize CRLF (\r\n) to LF (\n) — sse_starlette uses HTTP CRLF line endings
          buffer = buffer.replace(/\r\n/g, '\n');
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop();

          for (const block of blocks) {
            for (const line of block.split('\n')) {
              const trimmed = line.trim();
              if (trimmed.startsWith('data:')) {
                const jsonStr = trimmed.slice(5).trim();
                if (!jsonStr) continue;
                try {
                  const event = JSON.parse(jsonStr);
                  this.handleFollowupEvent(event, msgId);
                } catch (e) {
                  console.error('SSE Followup Parse Error:', e, jsonStr);
                }
              }
            }
          }

          processStream();
        }).catch(err => {
          console.error('Followup read error:', err);
          this.isGenerating = false;
        });
      };

      processStream();
    }).catch(err => {
      console.error('Followup fetch error:', err);
      this.isGenerating = false;
    });
  }

  handleFollowupEvent(event, msgId) {
    const { event: evType, payload } = event;
    const msgContainer = document.getElementById(msgId);
    if (!msgContainer) return;

    const cotBody = msgContainer.querySelector('.cot-body');
    const contentBody = msgContainer.querySelector('.message-prose');

    if (evType === 'router') {
      if (cotBody) {
        cotBody.textContent += `[ROUTER] Autonomous Route: ${payload.route} (${payload.reasoning})\n`;
      }
    } else if (evType === 'subsearch') {
      if (cotBody) {
        cotBody.textContent += `[LIVE PROBE] Executed search: "${payload.query}"\n`;
      }
    } else if (evType === 'mindmap_update') {
      if (payload.mindmap) {
        this.currentState.mindmap = payload.mindmap;
        this.renderMindMap(payload.mindmap);
      }
    } else if (evType === 'answer') {
      contentBody.innerHTML = marked.parse(payload.answer);
      if (payload.citations && payload.citations.length > 0) {
        this.renderCitations(msgContainer, payload.citations);
      }
    } else if (evType === 'report_expansion') {
      if (payload.updated_report) {
        this.currentState.report = payload.updated_report;
        this.renderReport(payload.updated_report);
      }
    } else if (evType === 'followup_complete') {
      this.currentState.chat_turns = payload.chat_turns;
      this.currentState.conversation_summary = payload.conversation_summary;
      if (payload.follow_up_questions) {
        this.renderProactivePills(msgContainer, payload.follow_up_questions);
      }
    }
  }

  // ============================================================================
  // UI RENDERING HELPERS
  // ============================================================================
  appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'chat-message-row user';
    row.innerHTML = `
      <div class="chat-avatar">
        <i data-lucide="user" style="width:18px;height:18px;color:#c99a6b;"></i>
      </div>
      <div class="chat-bubble">
        <div class="prose">${marked.parse(text)}</div>
      </div>
    `;
    this.chatFeed.appendChild(row);
    if (window.lucide) lucide.createIcons();
    if (window.ThothAnimations) window.ThothAnimations.animateNewMessage(row);
    this.scrollToBottom();
  }

  createAssistantPlaceholder(msgId) {
    const row = document.createElement('div');
    row.className = 'chat-message-row assistant';
    row.id = msgId;
    row.innerHTML = `
      <div class="chat-avatar">
        <img src="/assets/thoth_bust.jpg" alt="Thoth">
      </div>
      <div class="chat-bubble">
        <div class="cot-accordion">
          <div class="cot-header" onclick="ThothApp.toggleAccordion(this)">
            <span><i data-lucide="brain-circuit" style="width:14px;height:14px;vertical-align:middle;"></i> Cognitive Trace</span>
            <i data-lucide="chevron-down" style="width:14px;height:14px;"></i>
          </div>
          <div class="cot-body mono hidden"></div>
        </div>
        <div class="message-prose prose">
          <span style="color:hsl(var(--muted-foreground));"><i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;vertical-align:middle;"></i> Consulting the scrolls of Ma'at...</span>
        </div>
        <div class="citations-container"></div>
        <div class="proactive-container"></div>
      </div>
    `;
    this.chatFeed.appendChild(row);
    if (window.lucide) lucide.createIcons();
    if (window.ThothAnimations) window.ThothAnimations.animateNewMessage(row);
    this.scrollToBottom();
    return row;
  }

  static toggleAccordion(headerEl) {
    const bodyEl = headerEl.nextElementSibling;
    const isHidden = bodyEl.classList.contains('hidden');
    if (window.ThothAnimations) {
      window.ThothAnimations.animateAccordion(bodyEl, isHidden);
    } else {
      bodyEl.classList.toggle('hidden');
    }
  }

  renderProactivePills(containerEl, questions) {
    const proactiveContainer = containerEl.querySelector('.proactive-container');
    if (!proactiveContainer || !questions || !questions.length) return;

    proactiveContainer.innerHTML = `
      <div class="proactive-pills-row">
        ${questions.map(q => `<button class="followup-pill-btn" onclick="window.app.triggerPill('${q.replace(/'/g, "\\'")}')"><i data-lucide="sparkles" style="width:12px;height:12px;color:#c99a6b;"></i> ${q}</button>`).join('')}
      </div>
    `;
    if (window.lucide) lucide.createIcons();
  }

  triggerPill(questionText) {
    if (this.isGenerating) return;
    this.chatInput.value = questionText;
    this.handleChatSend();
  }

  renderCitations(containerEl, citations) {
    const citContainer = containerEl.querySelector('.citations-container');
    if (!citContainer || !citations || !citations.length) return;

    citContainer.innerHTML = `
      <div class="citations-footer">
        <span style="font-size:0.7rem;color:hsl(var(--muted-foreground));align-self:center;">Sources:</span>
        ${citations.map(c => `<a href="${c}" target="_blank" class="citation-chip"><i data-lucide="external-link" style="width:11px;height:11px;"></i> ${c.replace(/^https?:\/\//, '').split('/')[0]}</a>`).join('')}
      </div>
    `;
    if (window.lucide) lucide.createIcons();
  }

  renderReport(reportMarkdown) {
    if (this.artifactReportPane) {
      this.artifactReportPane.innerHTML = `
        <div class="prose">
          ${marked.parse(reportMarkdown)}
        </div>
      `;
    }
  }

  renderTruthGuard(verificationResults) {
    if (!this.artifactTruthPane) return;

    if (!verificationResults || !verificationResults.length) {
      this.artifactTruthPane.innerHTML = `<p style="color:hsl(var(--muted-foreground));font-size:0.85rem;">All extracted claims strictly verified against primary literature.</p>`;
      return;
    }

    const rows = verificationResults.map(res => `
      <tr>
        <td>${res.claim}</td>
        <td><span class="claim-status-badge ${res.is_valid ? 'valid' : 'invalid'}">${res.is_valid ? 'PASSED' : 'REVISED'}</span></td>
        <td class="mono" style="font-size:0.75rem;">${res.supporting_source_id || 'N/A'}</td>
      </tr>
    `).join('');

    this.artifactTruthPane.innerHTML = `
      <div style="margin-bottom:12px;">
        <h3 class="serif" style="color:hsl(var(--primary));margin-bottom:4px;">Scales of Ma'at Audit</h3>
        <p style="font-size:0.8rem;color:hsl(var(--muted-foreground));">Factual verification report validating claims against primary sources.</p>
      </div>
      <table class="truth-guard-table">
        <thead>
          <tr>
            <th>Atomic Claim</th>
            <th>Ma'at Verdict</th>
            <th>Attribution ID</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  renderSources(sources) {
    if (!this.artifactSourcesPane) return;
    if (!sources || !sources.length) {
      this.artifactSourcesPane.innerHTML = `<p style="color:hsl(var(--muted-foreground));font-size:0.85rem;">No sources cataloged yet.</p>`;
      return;
    }

    const items = sources.map((s, idx) => `
      <div style="background:hsl(var(--muted));border:1px solid hsl(var(--border));border-radius:var(--radius-md);padding:12px;display:flex;flex-direction:column;gap:6px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-weight:700;font-size:0.85rem;color:#fff;">${s.title || 'Source ' + (idx + 1)}</span>
          <span class="mono" style="font-size:0.7rem;color:hsl(var(--primary));">${s.source_api || 'web'}</span>
        </div>
        <div style="font-size:0.75rem;color:hsl(var(--muted-foreground));">${s.snippet || s.abstract || '(No abstract provided)'}</div>
        <a href="${s.url}" target="_blank" style="font-size:0.75rem;color:hsl(var(--primary));text-decoration:none;word-break:break-all;"><i data-lucide="external-link" style="width:12px;height:12px;vertical-align:middle;"></i> ${s.url}</a>
      </div>
    `).join('');

    this.artifactSourcesPane.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:12px;">
        ${items}
      </div>
    `;
    if (window.lucide) lucide.createIcons();
  }

  renderMindMap(mindmap) {
    if (!this.artifactMindmapPane) return;
    const nodes = mindmap.nodes || [];
    const edges = mindmap.edges || [];

    if (!nodes.length) {
      this.artifactMindmapPane.innerHTML = `<p style="color:hsl(var(--muted-foreground));font-size:0.85rem;">Mind map knowledge graph will construct upon synthesis.</p>`;
      return;
    }

    // Render Clean Interactive SVG
    const width = 420;
    const height = 340;
    const cx = width / 2;
    const cy = height / 2;

    // Calculate node coordinates in a circular radial layout
    const nodeCoords = {};
    nodes.forEach((n, idx) => {
      if (idx === 0) {
        nodeCoords[n.id] = { x: cx, y: cy, label: n.label, type: n.type || 'root' };
      } else {
        const angle = ((idx - 1) / (nodes.length - 1)) * (2 * Math.PI);
        const r = 110;
        nodeCoords[n.id] = {
          x: cx + r * Math.cos(angle),
          y: cy + r * Math.sin(angle),
          label: n.label,
          type: n.type || 'subtopic'
        };
      }
    });

    const edgeSvg = edges.map(e => {
      const from = nodeCoords[e.from] || nodeCoords['root'];
      const to = nodeCoords[e.to];
      if (!from || !to) return '';
      return `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" class="link-line" />`;
    }).join('');

    const nodeSvg = Object.keys(nodeCoords).map(id => {
      const n = nodeCoords[id];
      const isRoot = n.type === 'root' || n.type === 'topic';
      const r = isRoot ? 22 : 16;
      const fill = isRoot ? '#c99a6b' : '#1e293b';
      const stroke = isRoot ? '#dfb285' : '#c99a6b';

      return `
        <g class="node-group" transform="translate(${n.x}, ${n.y})">
          <circle r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="2" />
          <text y="${r + 14}" text-anchor="middle">${n.label.substring(0, 16)}</text>
        </g>
      `;
    }).join('');

    this.artifactMindmapPane.innerHTML = `
      <div class="mindmap-canvas-container">
        <svg class="mindmap-svg" viewBox="0 0 ${width} ${height}">
          ${edgeSvg}
          ${nodeSvg}
        </svg>
      </div>
      <div style="font-size:0.75rem;color:hsl(var(--muted-foreground));text-align:center;">
        Mapped ${nodes.length} concepts & ${edges.length} knowledge graph edges.
      </div>
    `;
  }

  // ============================================================================
  // VAULT NOTES EXPLORER
  // ============================================================================
  loadVaultNotes() {
    fetch('/api/vault/notes')
      .then(res => res.json())
      .then(data => {
        this.vaultNotes = data.notes || [];
        this.renderVaultNotesList(this.vaultNotes);
        const countEl = document.getElementById('vaultCountBadge');
        if (countEl) countEl.textContent = `${this.vaultNotes.length} notes`;
      })
      .catch(e => console.error('Failed to load vault notes:', e));
  }

  renderVaultNotesList(notes) {
    if (!this.vaultNotesList) return;
    if (!notes.length) {
      this.vaultNotesList.innerHTML = `<div style="padding:12px;font-size:0.75rem;color:hsl(var(--muted-foreground));">No notes in vault.</div>`;
      return;
    }

    this.vaultNotesList.innerHTML = notes.map(n => `
      <div class="vault-note-item" onclick="window.app.openNote('${n.id}')">
        <span class="note-type-badge ${n.type}">${n.type === 'topics' ? 'TOPIC' : 'SRC'}</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${n.id}</span>
      </div>
    `).join('');
  }

  filterVaultNotes(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
      this.renderVaultNotesList(this.vaultNotes);
      return;
    }
    const filtered = this.vaultNotes.filter(n => n.id.toLowerCase().includes(q));
    this.renderVaultNotesList(filtered);
  }

  openNote(noteId) {
    fetch(`/api/vault/note/${noteId}`)
      .then(res => res.json())
      .then(note => {
        if (this.modalTitle) this.modalTitle.textContent = note.id;
        if (this.modalBody) this.modalBody.innerHTML = marked.parse(note.content || '(Empty Note)');
        if (this.noteModal) this.noteModal.classList.remove('hidden');
      })
      .catch(e => console.error('Failed to fetch note:', e));
  }

  // ============================================================================
  // STEPPER UTILITIES
  // ============================================================================
  resetStepper() {
    if (!this.stepperBar) return;
    this.stepperBar.innerHTML = this.pipelineNodes.map(node => `
      <div class="step-node-badge" id="step_${node}">
        <span class="status-dot"></span>
        <span>${this.pipelineLabels[node]}</span>
      </div>
    `).join('');
  }

  updateStepperNode(activeNode) {
    let foundActive = false;
    this.pipelineNodes.forEach(node => {
      const el = document.getElementById(`step_${node}`);
      if (!el) return;

      if (node === activeNode) {
        el.className = 'step-node-badge active';
        const dot = el.querySelector('.status-dot');
        if (dot) dot.className = 'status-dot pulse';
        foundActive = true;
      } else if (!foundActive) {
        el.className = 'step-node-badge completed';
        const dot = el.querySelector('.status-dot');
        if (dot) dot.className = 'status-dot';
      } else {
        el.className = 'step-node-badge';
        const dot = el.querySelector('.status-dot');
        if (dot) dot.className = 'status-dot';
      }
    });
  }

  completeStepper() {
    this.pipelineNodes.forEach(node => {
      const el = document.getElementById(`step_${node}`);
      if (el) el.className = 'step-node-badge completed';
    });
  }

  scrollToBottom() {
    if (this.chatFeed) {
      this.chatFeed.scrollTop = this.chatFeed.scrollHeight;
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new ThothApp();
});
