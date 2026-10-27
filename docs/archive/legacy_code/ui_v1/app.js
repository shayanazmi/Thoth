class ThothApp {
  constructor() {
    this.currentView = 'landing';
    this.activeTopic = '';
    this.activeMode = 'auto';
    this.currentState = null;
    this.chatTurns = [];
    this.vaultNotes = [];
    this.activeArtifactTab = 'report';
    this.isGenerating = false;
    this.eventSource = null;

    this.pipelineNodes = ['search', 'snowball', 'scrape', 'prisma', 'writer', 'verifier', 'critic', 'vault', 'mindmap', 'manuscript'];
    this.pipelineLabels = {
      search: 'Searcher',
      snowball: 'Snowballer',
      scrape: 'Reader',
      prisma: 'PRISMA 2020',
      writer: 'Scribe',
      verifier: 'Truth Guard',
      critic: 'Critic',
      vault: 'Vault Indexer',
      mindmap: 'Mind Map',
      manuscript: 'Manuscript'
    };

    this.modeLabels = {
      fast_chat: { label: 'Chat', icon: 'message-square' },
      deep_research: { label: 'Deep Research', icon: 'microscope' },
      web_probe: { label: 'Web Probe', icon: 'globe' },
      local_qa: { label: 'Vault QA', icon: 'book-marked' },
      expand_report: { label: 'Expand Report', icon: 'file-plus' },
      auto: { label: 'Auto Router', icon: 'sparkles' },
      brainstorm: { label: 'Brainstorm', icon: 'brain' }
    };

    this.activeMode = 'fast_chat';
    this.brainstormTurns = [];
    this.selectedThinkerId = 'auto';

    this.scrapeTopN = parseInt(localStorage.getItem('thoth_scrape_top_n')) || 15;

    this.isUserScrolledUp = false;
    this.activeAbortController = null;

    this.initElements();
    this.bindEvents();
    this.setMode('fast_chat');
    this.setPaperVolume(this.scrapeTopN);
    this.loadVaultNotes();
  }

  _resolveUrl(endpoint) {
    if (window.ThothAPI && typeof window.ThothAPI.resolveUrl === 'function') {
      return window.ThothAPI.resolveUrl(endpoint);
    }
    const base = window.THOTH_CONFIG?.API_BASE_URL || '';
    return `${base}${endpoint}`;
  }

  async _getHeaders(contentType = 'application/json') {
    const headers = {};
    if (contentType) headers['Content-Type'] = contentType;
    if (window.ThothAuth && typeof window.ThothAuth.getAccessToken === 'function') {
      try {
        const token = await window.ThothAuth.getAccessToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
      } catch (e) {
        console.warn('Failed to retrieve auth token:', e);
      }
    }
    return headers;
  }

  initElements() {

    this.landingView = document.getElementById('landingView');
    this.studioView = document.getElementById('studioView');
    this.tabLandingBtn = document.getElementById('tabLandingBtn');
    this.tabStudioBtn = document.getElementById('tabStudioBtn');

    this.heroPromptInput = document.getElementById('heroPromptInput');
    this.heroLaunchBtn = document.getElementById('heroLaunchBtn');
    this.chatInput = document.getElementById('chatInput');
    this.chatSendBtn = document.getElementById('chatSendBtn');

    this.toolAttachBtn = document.getElementById('toolAttachBtn');
    this.floatingToolMenu = document.getElementById('floatingToolMenu');
    this.activeModeBadge = document.getElementById('activeModeBadge');
    this.activeModeLabel = document.getElementById('activeModeLabel');
    this.deepResearchToggle = document.getElementById('deepResearchToggle');
    this.brainstormToggle = document.getElementById('brainstormToggle');
    this.brainstormSelectorBar = document.getElementById('brainstormSelectorBar');
    this.thinkerSelect = document.getElementById('thinkerSelect');
    this.thinkerArchetypeLabel = document.getElementById('thinkerArchetypeLabel');

    this.paperVolumeBadge = document.getElementById('paperVolumeBadge');
    this.paperVolumeLabel = document.getElementById('paperVolumeLabel');
    this.heroVolumeGroup = document.getElementById('heroVolumeGroup');
    this.paperVolumeOptionsGrid = document.getElementById('paperVolumeOptionsGrid');

    this.chatFeed = document.getElementById('chatFeed');
    this.jumpToLatestBtn = document.getElementById('jumpToLatestBtn');
    this.stepperBar = document.getElementById('pipelineStepperBar');
    this.currentTopicDisplay = document.getElementById('currentTopicDisplay');
    this.vaultNotesList = document.getElementById('vaultNotesList');
    this.vaultSearchInput = document.getElementById('vaultSearchInput');

    this.artifactReportPane = document.getElementById('artifactReportPane');
    this.artifactPrismaPane = document.getElementById('artifactPrismaPane');
    this.artifactManuscriptPane = document.getElementById('artifactManuscriptPane');
    this.artifactTruthPane = document.getElementById('artifactTruthPane');
    this.artifactMindmapPane = document.getElementById('artifactMindmapPane');
    this.artifactSourcesPane = document.getElementById('artifactSourcesPane');

    this.noteModal = document.getElementById('noteModal');
    this.modalTitle = document.getElementById('modalTitle');
    this.modalBody = document.getElementById('modalBody');
    this.modalCloseBtn = document.getElementById('modalCloseBtn');
  }

  bindEvents() {

    if (window.ThothAnimations) {
      window.ThothAnimations.init3DParallax();
    }

    this.tabLandingBtn?.addEventListener('click', () => this.switchView('landing'));
    this.tabStudioBtn?.addEventListener('click', () => this.switchView('studio'));

    this.heroLaunchBtn?.addEventListener('click', () => this.handleHeroLaunch());
    this.heroPromptInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.handleHeroLaunch();
    });

    document.querySelectorAll('.preset-chip').forEach(chip => {
      chip.addEventListener('click', (e) => {
        const query = e.target.getAttribute('data-query');
        if (query) {
          this.heroPromptInput.value = query;
          this.handleHeroLaunch();
        }
      });
    });

    document.querySelectorAll('.volume-chip').forEach(chip => {
      chip.addEventListener('click', (e) => {
        const vol = parseInt(e.currentTarget.getAttribute('data-volume'));
        if (vol) this.setPaperVolume(vol);
      });
    });

    this.chatInput?.addEventListener('input', () => this.autoResizeTextarea());
    this.chatSendBtn?.addEventListener('click', () => this.handleChatSend());
    this.chatInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleChatSend();
      }
    });

    this.chatFeed?.addEventListener('scroll', () => {
      const threshold = 100;
      const distFromBottom = this.chatFeed.scrollHeight - this.chatFeed.scrollTop - this.chatFeed.clientHeight;
      this.isUserScrolledUp = distFromBottom > threshold;
      if (!this.isUserScrolledUp && this.jumpToLatestBtn) {
        this.jumpToLatestBtn.classList.add('hidden');
      }
    });

    this.jumpToLatestBtn?.addEventListener('click', () => {
      this.isUserScrolledUp = false;
      this.scrollToBottom(true);
    });

    this.toolAttachBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleToolMenu();
    });
    this.activeModeBadge?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleToolMenu();
    });
    this.paperVolumeBadge?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleToolMenu();
    });

    document.addEventListener('click', (e) => {
      if (this.floatingToolMenu && !this.floatingToolMenu.contains(e.target) && e.target !== this.toolAttachBtn && e.target !== this.activeModeBadge && e.target !== this.paperVolumeBadge) {
        this.floatingToolMenu.classList.add('hidden');
      }
    });

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

    document.querySelectorAll('.volume-option-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const vol = parseInt(e.currentTarget.getAttribute('data-volume'));
        if (vol) {
          this.setPaperVolume(vol);
          this.floatingToolMenu?.classList.add('hidden');
        }
      });
    });

    this.deepResearchToggle?.addEventListener('click', () => {
      if (this.activeMode === 'deep_research') {
        this.setMode('fast_chat');
      } else {
        this.setMode('deep_research');
      }
    });

    this.brainstormToggle?.addEventListener('click', () => {
      if (this.activeMode === 'brainstorm') {
        this.setMode('fast_chat');
      } else {
        this.setMode('brainstorm');
      }
    });

    this.thinkerSelect?.addEventListener('change', (e) => {
      this.handleThinkerSelectChange(e.target.value);
    });

    document.querySelectorAll('.artifact-tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tab = e.target.getAttribute('data-tab');
        this.switchArtifactTab(tab);
      });
    });

    this.vaultSearchInput?.addEventListener('input', (e) => {
      this.filterVaultNotes(e.target.value);
    });

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
      prisma: this.artifactPrismaPane,
      manuscript: this.artifactManuscriptPane,
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
    if (tabName === 'prisma' && this.currentState?.prisma_review) {
      this.renderPrismaPane(this.currentState.prisma_review);
    }
    if (tabName === 'manuscript' && (this.currentState?.manuscript || this.currentState?.revision)) {
      this.renderManuscriptPane(this.currentState.manuscript, this.currentState.revision, this.currentState.project_id);
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
    const isBrainstorm = mode === 'brainstorm';

    if (this.activeModeLabel) {
      this.activeModeLabel.textContent = info.label;
    }
    if (this.activeModeBadge) {
      this.activeModeBadge.innerHTML = `<i data-lucide="${info.icon}" style="width:12px;height:12px;"></i> <span>${info.label}</span> <i data-lucide="chevron-down" style="width:10px;height:10px;opacity:0.6;"></i>`;
    }
    if (this.deepResearchToggle) {
      this.deepResearchToggle.classList.toggle('active', isResearch);
    }
    if (this.brainstormToggle) {
      this.brainstormToggle.classList.toggle('active', isBrainstorm);
    }
    if (this.brainstormSelectorBar) {
      this.brainstormSelectorBar.classList.toggle('hidden', !isBrainstorm);
    }

    if (this.chatSendBtn) {
      const sendIcon = isResearch ? 'zap' : (isBrainstorm ? 'brain' : 'arrow-up');
      this.chatSendBtn.innerHTML = `<i data-lucide="${sendIcon}" style="width:15px;height:15px;"></i>`;
      this.chatSendBtn.title = isResearch ? 'Launch Research Swarm' : (isBrainstorm ? 'Spar with Thinker' : 'Send Message');
      if (isResearch) {
        this.chatSendBtn.style.background = 'linear-gradient(135deg, hsl(32, 65%, 48%), hsl(42, 80%, 55%))';
      } else if (isBrainstorm) {
        this.chatSendBtn.style.background = 'linear-gradient(135deg, #c99a6b, #8a5a2b)';
      } else {
        this.chatSendBtn.style.background = '';
      }
    }

    document.querySelectorAll('.tool-menu-item').forEach(el => {
      el.classList.toggle('active', el.getAttribute('data-mode') === mode);
    });

    if (window.lucide) lucide.createIcons();

    const placeholders = {
      deep_research: 'Enter a topic to trigger the 8-agent research swarm & vault synthesis...',
      brainstorm: 'Spar with the philosopher on your dilemma, hypothesis, or assumptions...',
      web_probe: 'Enter query for live targeted arXiv & web literature search...',
      local_qa: 'Ask a question over your indexed Obsidian notes & research report...',
      expand_report: 'Describe the section or comparison you want added to the report...',
      fast_chat: 'Ask Thoth anything — chat, explain, discuss...'
    };
    if (this.chatInput) {
      this.chatInput.placeholder = placeholders[mode] || 'Ask Thoth anything...';
    }
  }

  setGenerating(isGen) {
    this.isGenerating = isGen;
    const isResearch = this.activeMode === 'deep_research';

    if (this.chatSendBtn) {
      if (isGen) {
        this.chatSendBtn.classList.add('btn-stop-generating');
        this.chatSendBtn.innerHTML = `<i data-lucide="square" style="width:11px;height:11px;fill:currentColor;"></i> <span>Stop</span>`;
        this.chatSendBtn.title = 'Stop Generation';
      } else {
        this.chatSendBtn.classList.remove('btn-stop-generating');
        this.chatSendBtn.innerHTML = `<i data-lucide="${isResearch ? 'zap' : 'arrow-up'}" style="width:15px;height:15px;"></i>`;
        this.chatSendBtn.title = isResearch ? 'Launch Research Swarm' : 'Send Message';
        this.chatSendBtn.style.background = isResearch
          ? 'linear-gradient(135deg, hsl(32, 65%, 48%), hsl(42, 80%, 55%))'
          : '';
        this.activeAbortController = null;
      }
    }
    if (window.lucide) lucide.createIcons();
  }

  abortGeneration() {
    if (this.activeAbortController) {
      this.activeAbortController.abort();
      this.activeAbortController = null;
    }
    const currentId = this.currentState?.task_id || this.currentState?.brief?.brief_id;
    if (currentId) {
      this._getHeaders().then(headers => {
        fetch(this._resolveUrl('/api/research/cancel'), {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ task_id: currentId, brief_id: currentId })
        }).catch(() => {});
      });
    }
    this.setGenerating(false);
    this.showToast('Generation cancelled', 'alert-circle');
  }

  autoResizeTextarea() {
    if (!this.chatInput) return;
    this.chatInput.style.height = 'auto';
    const newHeight = Math.min(Math.max(this.chatInput.scrollHeight, 38), 160);
    this.chatInput.style.height = `${newHeight}px`;
  }

  setPaperVolume(n) {
    const validCount = Math.max(3, Math.min(parseInt(n) || 15, 50));
    this.scrapeTopN = validCount;
    localStorage.setItem('thoth_scrape_top_n', validCount);

    if (this.paperVolumeLabel) {
      this.paperVolumeLabel.textContent = validCount === 15 ? 'Top 15 Papers' : `${validCount} Papers`;
    }

    document.querySelectorAll('.volume-chip').forEach(chip => {
      chip.classList.toggle('active', parseInt(chip.getAttribute('data-volume')) === validCount);
    });

    document.querySelectorAll('.volume-option-btn').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.getAttribute('data-volume')) === validCount);
    });

    if (window.lucide) lucide.createIcons();
  }

  handleThinkerSelectChange(thinkerId) {
    this.selectedThinkerId = thinkerId;
    const labels = {
      auto: 'Auto Mode: Diagnoses Root Bottleneck',
      aristotle: 'Aristotle: Categorical & Causal Architect',
      descartes: 'Descartes: Foundational Reductionist',
      bacon: 'Bacon: Eliminative Empiricist',
      hume: 'Hume: Causal Skeptic & Confounder Detector',
      darwin: 'Darwin: Evolutionary Selectionist',
      popper: 'Popper: Falsificationist Warrior',
      kuhn: 'Kuhn: Paradigmatic Strategist',
      box: 'Box: Pragmatic Modeling Iterativist',
      turing: 'Turing: Computational Operationalist',
      simon: 'Simon: Bounded Rationalist'
    };
    if (this.thinkerArchetypeLabel) {
      this.thinkerArchetypeLabel.textContent = labels[thinkerId] || labels.auto;
    }
  }

  async sendBrainstormMessage(text) {
    this.setGenerating(true);
    if (!this.brainstormTurns) this.brainstormTurns = [];

    const thinkerId = this.selectedThinkerId || (this.thinkerSelect ? this.thinkerSelect.value : 'auto');

    const msgRow = document.createElement('div');
    msgRow.className = 'chat-message-row assistant';
    msgRow.innerHTML = `
      <div class="chat-avatar"><img src="/assets/thoth_bust.jpg" alt="Thinker"></div>
      <div class="chat-bubble">
        <div class="thinker-chat-badge"><i data-lucide="brain" style="width:11px;height:11px;"></i> Sparring in progress...</div>
        <div class="streaming-cursor"></div>
      </div>
    `;
    this.chatFeed.appendChild(msgRow);
    this.scrollToBottom(true);
    if (window.lucide) lucide.createIcons();

    try {
      const resp = await fetch(this._resolveUrl('/api/brainstorm/chat'), {
        method: 'POST',
        headers: await this._getHeaders(),
        body: JSON.stringify({
          thinker_id: thinkerId,
          message: text,
          chat_turns: this.brainstormTurns
        })
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      this.brainstormTurns.push({ user: text, assistant: data.reply });

      let badgeLabel = `${data.thinker_name} · ${data.archetype}`;
      if (data.auto_match) {
        badgeLabel = `⚡ Auto-Matched: ${data.thinker_name} (${data.archetype})`;
      }

      let contentHtml = `
        <div class="thinker-chat-badge">
          <i data-lucide="award" style="width:11px;height:11px;"></i> ${badgeLabel}
        </div>
        <div class="prose">${marked.parse(data.reply)}</div>
      `;

      if (data.escalation_proposal && data.escalation_proposal.is_ready_for_research) {
        const p = data.escalation_proposal;
        const encodedTopic = encodeURIComponent(p.crystallized_topic || text);
        const encodedHyp = encodeURIComponent(p.testable_hypothesis || '');
        const encodedThinker = encodeURIComponent(data.thinker_id || '');
        contentHtml += `
          <div class="escalation-action-card">
            <div class="escalation-header">
              <i data-lucide="sparkles" style="width:14px;height:14px;color:#c99a6b;"></i>
              <span>Hypothesis Crystallized · Ready for Deep Research</span>
            </div>
            <div class="escalation-topic"><strong>Target Topic:</strong> ${p.crystallized_topic}</div>
            <div class="escalation-hypothesis"><strong>Hypothesis:</strong> ${p.testable_hypothesis}</div>
            <button class="btn-launch-escalated-research" onclick="window.app.launchEscalatedResearch('${encodedTopic}', '${encodedThinker}', '${encodedHyp}')">
              <i data-lucide="rocket" style="width:14px;height:14px;"></i>
              <span>${p.action_pill_label || 'Launch Deep Research'}</span>
            </button>
          </div>
        `;
      }

      msgRow.querySelector('.chat-bubble').innerHTML = contentHtml;
      if (window.lucide) lucide.createIcons();
      this.scrollToBottom(true);

    } catch (err) {
      msgRow.querySelector('.chat-bubble').innerHTML = `
        <div class="prose" style="color:#f87171;">
          <p><strong>Sparring Error:</strong> ${err.message}</p>
        </div>
      `;
    } finally {
      this.setGenerating(false);
    }
  }

  launchEscalatedResearch(encodedTopic, thinkerId, encodedHyp) {
    const topic = decodeURIComponent(encodedTopic);
    const thinker = decodeURIComponent(thinkerId || '');
    const hypothesis = decodeURIComponent(encodedHyp || '');
    this.showToast(`Preparing research brief with ${thinker || 'Thinker'} rigour...`, 'sparkles');
    this.setMode('deep_research');
    this.startResearch(topic, true, true, { thinker_id: thinker, hypothesis: hypothesis });
  }

  approveAndLaunchBrief(briefId, version, encodedTopic) {
    const topic = decodeURIComponent(encodedTopic || this.activeTopic || '');
    this.showToast('Approving research brief...', 'check-circle');
    this._getHeaders().then(headers => {
      fetch(this._resolveUrl('/api/research/brief/approve'), {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ brief_id: decodeURIComponent(briefId), version: parseInt(version) })
      })
      .then(res => res.json())
      .then(data => {
        if (data.success && data.brief) {
          this.showToast('Research Brief approved! Launching research...', 'rocket');
          this.startResearch(topic, false, true, { brief_id: data.brief.brief_id });
        } else {
          this.showToast(data.error || 'Failed to approve brief', 'alert-triangle');
        }
      })
      .catch(err => {
        console.error('Approval error:', err);
        this.showToast('Approval request failed: ' + err.message, 'alert-triangle');
      });
    });
  }

  handleHeroLaunch() {
    const topic = this.heroPromptInput.value.trim();
    if (!topic || this.isGenerating) return;
    this.switchView('studio');
    // Unified surface (vision §2): the server classifies the turn; no mode lanes.
    this.heroPromptInput.value = '';
    this.appendUserMessage(topic);
    this.sendUnifiedTurn(topic);
  }

  isResearchDirective(text) {
    if (!text || typeof text !== 'string') return false;
    const clean = text.trim().toLowerCase().replace(/[?!.,;:]+$/, '');

    if (/^(what|why|how|who|when|where|is|are|was|were)\s+(is\s+|are\s+)?(research|investigation)\b/.test(clean)) {
      return false;
    }

    const directivePatterns = [
      /^(do\s+|conduct\s+|run\s+|start\s+)?deep\s+research(\s+on|\s+into|\s+about)?/i,
      /^(can\s+you\s+|please\s+|go\s+)?(research|investigate|dig\s+into|look\s+into|examine|explore)(\s+this|\s+that|\s+it|\s+the\s+above|\s+further|\s+properly|\s+deeply)?(\s+on|\s+into|\s+about)?/i,
      /^(go\s+deeper|explore\s+deeply|explore\s+in\s+depth|dig\s+deeper)(\s+on|\s+into|\s+about|\s+this|\s+that|\s+it)?/i,
      /^(find|gather)\s+(evidence|literature|papers|sources|data)\s+(for|on|about|regarding)/i,
      /^(what\s+does\s+the\s+(research|literature|evidence)\s+say(\s+about)?)/i,
      /^research:/i
    ];

    return directivePatterns.some(pattern => pattern.test(clean));
  }

  handleChatSend() {
    // Phase 1 unified entrypoint (vision §2, §10).
    // No modes: the server classifies the turn and emits typed cards.
    const text = this.chatInput.value.trim();
    // Vision §10: the conversation stays live during a run — text always sends.
    if (this.isGenerating && !text) {
      this.abortGeneration();
      return;
    }
    if (!text) return;

    this.chatInput.value = '';
    this.autoResizeTextarea();

    if (text.startsWith('/')) {
      this.handleSlashCommand(text);
      return;
    }

    this.appendUserMessage(text);
    if (/^approve\b/i.test(text) && this._pendingBrief) {
      this.approvePendingBrief();
      return;
    }
    // Phase 3: "run a formal review" escalates the last plan; the server needs its brief_id.
    const wantsFormal = /\b(run|do|start|launch|begin|proceed with|go (?:for|with|ahead with)|want|need|let'?s do)\b[^?]{0,40}?\b(formal|systematic|prisma|proper|full)\b[^?]{0,20}?\breview\b/i.test(text);
    this.sendUnifiedTurn(text, wantsFormal && this._lastBriefId ? { brief_id: this._lastBriefId } : {});
  }

  approvePendingBrief() {
    // Vision §2/§10: explicit approval of the exact brief version shown.
    const pending = this._pendingBrief;
    if (!pending) {
      this.appendAssistantMessage('There is no plan waiting for approval.');
      return;
    }
    this._pendingBrief = null;
    this._disableCardButtons('.approve-btn');
    this.sendUnifiedTurn('', { approval: { brief_id: pending.brief_id, approved_version: pending.approved_version } });
  }

  /**
   * Phase 1 — unified conversational turn.
   * POSTs to /api/chat/stream and dispatches SSE events to card renderers.
   * Vision §10: the input stays live during a run (setGenerating only swaps the icon).
   */
  async sendUnifiedTurn(text, extras = {}) {
    this.setGenerating(true);
    try {
      const body = {
        message: text,
        session_id: this.sessionId || '',
        chat_turns: (this.currentState && this.currentState.chat_turns) || [],
        conversation_summary: (this.currentState && this.currentState.conversation_summary) || '',
        ...extras,
      };
      const resp = await fetch(this._resolveUrl('/api/chat/stream'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        this.appendAssistantMessage(`Could not reach Thoth: ${resp.status}`);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        // sse-starlette frames lines with CRLF; normalise before splitting.
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        let idx;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const dataLines = frame.split('\n').filter(l => l.startsWith('data: '));
          if (!dataLines.length) continue;
          try {
            const payload = JSON.parse(dataLines.map(l => l.slice(6)).join('\n'));
            this.renderChatEvent(payload);
          } catch (_) {}
        }
      }
    } catch (err) {
      this.appendAssistantMessage(`A hiccup reaching Thoth: ${err && err.message || err}`);
    } finally {
      this.setGenerating(false);
    }
  }

  /**
   * Render a card for one SSE event from /api/chat/stream. Minimum viable Phase 1
   * — later phases add richer card types (lightweight scan, originality verdict, etc.).
   */
  _disableCardButtons(selector) {
    document.querySelectorAll(selector).forEach(b => { b.disabled = true; });
  }

  async promoteIdeaCandidate(title, hypothesis, rationale) {
    this._disableCardButtons('.idea-btn');
    // Phase 2 (vision §3.1): one explicit user action promotes a detected
    // candidate. Reuses the unified chat endpoint — the server records the
    // TENTATIVE → PROMOTED lifecycle atomically.
    await this.sendUnifiedTurn('', {
      idea_promotion: {
        title: title,
        hypothesis: hypothesis,
        rationale: rationale,
      },
    });
  }

  dismissIdeaCandidate() {
    this._pendingIdea = null;
    this._disableCardButtons('.idea-btn');
    this.appendAssistantMessage('_Noted. I won\'t capture that one._');
  }

    renderChatEvent(evt) {
    if (!evt || typeof evt !== 'object') return;
    const kind = evt.event;
    const p = evt.payload || {};
    switch (kind) {
      case 'turn_start':
      case 'plan_preparing':
        // Non-blocking prep indicator. One ephemeral badge is enough.
        if (kind === 'plan_preparing' && p.note) {
          this.appendAssistantMessage(`_${p.note}_`);
        }
        break;
      case 'direct_answer':
        this.appendAssistantMessage(p.answer || '');
        break;
      case 'clarification_needed': {
        const prompt = p.prompt || 'Could you say a bit more?';
        const opts = Array.isArray(p.options) ? p.options : [];
        const optList = opts.length ? '\n\n' + opts.map(o => `• ${o}`).join('\n') : '';
        this.appendAssistantMessage(`${prompt}${optList}`);
        break;
      }
      case 'plan_pending': {
        const brief = p.brief || {};
        const q = brief.research_question || brief.topic || '';
        const objs = (brief.objectives || []).slice(0, 3);
        const objList = objs.length ? '\n\n' + objs.map(o => `- ${o}`).join('\n') : '';
        const cost = p.cost_estimate || {};
        const mode = (brief.review_mode || 'scan') === 'formal' ? 'Formal PRISMA-aligned review' : 'Lightweight literature scan';
        const costLines = cost.review_mode
          ? `\n\n**Mode:** ${mode} (v${brief.version})\n\n**Estimated effort:** ${cost.papers_considered} · full texts: ${cost.full_text_attempts} · ${cost.llm_calls} LLM calls · ${cost.typical_duration}`
          : '';
        const text =
          `**I've sketched a plan.** Review it and approve when you're ready — the chat stays live.\n\n` +
          `**Question:** ${q}${objList}${costLines}\n\n` +
          `<button type="button" class="proactive-pill approve-btn" onclick="window.app.approvePendingBrief()">Approve this plan</button>` +
          `  _or reply "approve"._`;
        this.appendAssistantMessage(text);
        this._lastBriefId = brief.brief_id;
        // Stash the pending brief so a plain "approve" from the user can hand it back.
        this._pendingBrief = { brief_id: brief.brief_id, approved_version: brief.version };
        break;
      }
      case 'idea_candidate': {
        const cand = p.candidate || {};
        const title = cand.title || 'Possible research direction';
        const trigger = cand.trigger_label || '';
        const rationale = cand.rationale || p.guidance || '';
        // Stash so a short "promote" reply from the user can hand it back without re-typing.
        this._pendingIdea = {
          title: cand.title,
          hypothesis: cand.hypothesis,
          rationale: cand.rationale,
        };
        const safeTitle = (cand.title || '').replace(/'/g, "\\'");
        const safeHypothesis = (cand.hypothesis || '').replace(/'/g, "\\'");
        const safeRationale = (cand.rationale || '').replace(/'/g, "\\'");
        const html =
          `**Idea worth capturing?** ${title}\n\n` +
          (trigger ? `_${trigger}_\n\n` : '') +
          `${rationale}\n\n` +
          `<button type="button" class="proactive-pill idea-btn" ` +
          `onclick="window.app.promoteIdeaCandidate('${safeTitle}', '${safeHypothesis}', '${safeRationale}')">Promote to idea network</button>` +
          `  <button type="button" class="proactive-pill idea-btn" onclick="window.app.dismissIdeaCandidate()">Not now</button>`;
        this.appendAssistantMessage(html);
        break;
      }
      case 'idea_promoted': {
        const idea = p.idea || {};
        this._pendingIdea = null;
        this.appendAssistantMessage(`✓ Added **${idea.title || 'idea'}** to your idea network.`);
        break;
      }
      case 'approval_recorded':
        this.appendAssistantMessage(`✓ Approved (v${p.approved_version}). Starting the research pass — the chat stays live.`);
        break;
      case 'approval_rejected':
        this.appendAssistantMessage(`Approval could not be recorded: ${p.reason || 'unknown reason'}`);
        break;
      case 'approval_verified':
        this.appendAssistantMessage(`_Research pass running on plan v${p.version}…_`);
        break;
      case 'search':
        this.appendAssistantMessage(`_Searching scholarly databases… found ${(p.cumulative_sources || []).length} candidate sources._`);
        break;
      case 'scan_result': {
        this._progressShown = {};
        const papers = (p.papers || []).slice(0, 8).map(x => `- ${x.title}${x.year ? ` (${x.year})` : ''} — _${x.reading_depth}_`).join('\n');
        this.appendAssistantMessage(`**Lightweight scan:** ${p.paper_count} papers (cap ${p.cap}).\n\n${papers}\n\n_${p.reading_depth_note}_`);
        break;
      }
      case 'recommend_formal_review': {
        const reasons = (p.reasons || []).map(r => `- ${r}`).join('\n');
        const e = p.effort || {};
        this.appendAssistantMessage(`**I'd recommend a formal review.**\n\n${reasons}\n\n**Extra effort:** ${e.papers_considered} · ${e.full_text_attempts} · ${e.typical_duration}\n\n_${p.guidance}_`);
        break;
      }
      case 'prisma': {
        this._progressShown = {};
        const c = (p.prisma_review || {}).flow_counts || {};
        this.appendAssistantMessage(`**Formal PRISMA review recorded.** Identified ${c.total_identified ?? '?'} · screened ${c.records_screened ?? '?'} · included ${c.included_reports ?? '?'} reports. Counts come from the actual recorded ledger.`);
        break;
      }
      case 'final_report':
        this._lastReport = null;
        if (p.report) this.appendAssistantMessage(p.report);
        break;
      case 'thinker_perspective': {
        // Show the drafted report first, then the critical passes on it.
        if (this._lastReport) { this.appendAssistantMessage(this._lastReport); this._lastReport = null; }
        if (!p.invoked) { this.appendAssistantMessage(`_Thinker check: ${p.reason}_`); break; }
        this.appendAssistantMessage(
          `**${p.thinker_name}'s perspective** (${p.stage.replace('_', ' ')})\n\n_Why this thinker:_ ${p.why_this_thinker || ''}\n\n> ${p.opening_challenge || ''}` +
          (p.verdict ? `\n\n**Verdict:** ${p.verdict} · severity gate: ${p.gate_severity} (advisory — no veto)` : '') +
          (p.review_error ? `\n\n_${p.review_error}_` : ''));
        break;
      }
      case 'originality_assessment': {
        const prior = (p.closest_prior_work || []).slice(0, 3).map(x => `- ${x.title} (overlap ${x.overlap})`).join('\n');
        this.appendAssistantMessage(
          `**Originality:** \`${p.verdict}\`\n\n${p.explanation || ''}` +
          (p.adjacent_queries ? `\n\n_Adjacent-field searches:_ ${p.adjacent_queries.join(' · ')} → ${p.adjacent_results} results` : '') +
          (prior ? `\n\n**Closest prior work:**\n\n${prior}` : '') +
          (p.limits ? `\n\n_${p.limits}_` : ''));
        break;
      }
      case 'report_status': {
        const counts = Object.entries(p.claim_counts || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'none audited';
        const gaps = (p.gaps || []).map(g => `- ${g}`).join('\n');
        const badge = p.report_status === 'fully_reviewed' ? '✅ FULLY REVIEWED' : '🟡 PROVISIONAL';
        this.appendAssistantMessage(`**Report status: ${badge}**\n\n**Claims:** ${counts}${gaps ? `\n\n**Open gaps:**\n\n${gaps}` : ''}\n\n_${p.pdf_export}_`);
        break;
      }
      case 'writer':
      case 'verifier':
      case 'critic':
      case 'scrape':
      case 'snowball':
      case 'vault':
      case 'mindmap':
      case 'manuscript':
        // Intermediate drafts and bookkeeping stay out of the chat; the final report is shown via follow_up.
        if (kind === 'writer') this._lastReport = p.report || this._lastReport;
        // Keep the user informed during the long write/verify stretch (one line per stage, not per retry).
        if ((kind === 'writer' || kind === 'verifier') && !(this._progressShown || {})[kind]) {
          this._progressShown = { ...(this._progressShown || {}), [kind]: true };
          this.appendAssistantMessage(kind === 'writer'
            ? '_Drafting the synthesis from the sources…_'
            : '_Checking each claim against its source (Truth Guard) and scoring the draft…_');
        }
        break;
      case 'follow_up':
        if (this._lastReport) this.appendAssistantMessage(this._lastReport);
        if (Array.isArray(p.follow_up_questions) && p.follow_up_questions.length) {
          this.appendAssistantMessage('**Where we could go next:**\n\n' + p.follow_up_questions.map(q => `- ${q}`).join('\n'));
        }
        break;
      case 'error':
        this.appendAssistantMessage(`⚠ ${p.error || 'An error occurred.'}`);
        break;
      case 'complete':
        // Nothing to render for a clean completion.
        break;
      default:
        // Pipeline nodes (search, scrape, writer, truth_guard, …) — render as discreet log lines.
        if (p && (p.report || p.answer || p.summary)) {
          this.appendAssistantMessage(p.report || p.answer || p.summary);
        }
        break;
    }
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

      this.sendFollowup(cmd);
    }
  }

  startResearch(topic, shouldAppendUser = true, inheritContext = true, extraMeta = {}) {
    this.activeTopic = topic;
    this.setGenerating(true);
    this.activeAbortController = new AbortController();
    this.currentTopicDisplay.textContent = topic;
    if (this.stepperBar) this.stepperBar.innerHTML = '';

    if (shouldAppendUser) {
      this.appendUserMessage(topic);
    }

    const paperMatch = topic.match(/\b(?:top|scrape|fetch|analyze|with)\s+(\d{1,2})\s+papers?\b/i);
    if (paperMatch) {
      const extractedCount = parseInt(paperMatch[1]);
      if (extractedCount >= 3 && extractedCount <= 50) {
        this.setPaperVolume(extractedCount);
      }
    }

    const msgId = `msg_${Date.now()}`;
    const bubbleEl = this.createAssistantPlaceholder(msgId);

    const payload = {
      topic: topic,
      mode: 'deep_research',
      role: "senior academic researcher",
      tone: "formal and analytical",
      scrape_top_n: this.scrapeTopN || 15,
      min_score: 6.5,
      chat_turns: (inheritContext && this.currentState?.chat_turns) ? this.currentState.chat_turns : [],
      conversation_summary: (inheritContext && this.currentState?.conversation_summary) ? this.currentState.conversation_summary : '',
      thinker_id: extraMeta?.thinker_id || this.activeThinker || undefined,
      hypothesis: extraMeta?.hypothesis || undefined,
      brief_id: extraMeta?.brief_id || undefined
    };

    this._getHeaders().then(headers => {
      fetch(this._resolveUrl('/api/research/stream'), {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        signal: this.activeAbortController.signal
      }).then(response => {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processStream = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            this.setGenerating(false);
            this.loadVaultNotes();
            return;
          }

          buffer += decoder.decode(value, { stream: true });

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
                  this.handlePipelineEvent(event, msgId);
                } catch (e) {
                  console.error('SSE Parse Error:', e, jsonStr);
                }
              }
            }
          }

          processStream();
        }).catch(err => {
          if (err.name === 'AbortError') {
            console.log('Research stream cancelled by user.');
            return;
          }
          console.error('SSE Stream read error:', err);
          this.setGenerating(false);
          const bubbleEl = document.getElementById(msgId);
          if (bubbleEl) {
            const prose = bubbleEl.querySelector('.message-prose');
            if (prose && (!this.currentState || !this.currentState.report)) {
              prose.innerHTML = `<span style="color:hsl(var(--destructive));font-size:0.9rem;"><i data-lucide="alert-triangle" style="width:14px;height:14px;vertical-align:middle;margin-right:6px;"></i> Research connection interrupted.</span>`;
              if (window.lucide) lucide.createIcons();
            }
          }
          this.showToast('Research stream interrupted', 'alert-triangle');
        });
      };

      processStream();
    }).catch(err => {
      if (err.name === 'AbortError') return;
      console.error('Fetch error:', err);
      this.setGenerating(false);
      const bubbleEl = document.getElementById(msgId);
      if (bubbleEl) {
        const prose = bubbleEl.querySelector('.message-prose');
        if (prose) {
          prose.innerHTML = `<span style="color:hsl(var(--destructive));font-size:0.9rem;"><i data-lucide="alert-triangle" style="width:14px;height:14px;vertical-align:middle;margin-right:6px;"></i> Unable to connect to research server.</span>`;
          if (window.lucide) lucide.createIcons();
        }
      }
      this.showToast('Failed to start research', 'alert-triangle');
    });
    });
  }

  renderBriefHtml(brief, reason) {
    if (!brief || !brief.brief_id) {
      return `
        <div class="brief-card" style="padding:16px;border-radius:var(--radius-lg);background:hsl(var(--card));border:1px solid hsl(var(--border));box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:12px;">
          <div style="font-weight:600;font-size:0.95rem;color:hsl(var(--destructive));"><i data-lucide="shield-alert" style="width:16px;height:16px;vertical-align:middle;margin-right:6px;"></i>Research Approval Barrier</div>
          <p style="font-size:0.85rem;color:hsl(var(--muted-foreground));margin-top:6px;">${reason || 'Formal research requires an explicit, approved Research Brief.'}</p>
        </div>
      `;
    }

    const version = brief.version || 1;
    const briefId = brief.brief_id;
    const status = brief.approval_status || 'pending_approval';
    const isApproved = status === 'approved';
    const topic = brief.topic || this.activeTopic || '';
    const safeTopic = topic.replace(/'/g, "\\'");

    let objectivesHtml = '';
    if (brief.objectives && brief.objectives.length > 0) {
      objectivesHtml = `
        <div style="margin-top:8px;">
          <div style="font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:hsl(var(--muted-foreground));margin-bottom:4px;">Core Objectives</div>
          <ul style="margin:0;padding-left:18px;font-size:0.85rem;color:hsl(var(--foreground));">
            ${brief.objectives.map(obj => `<li style="margin-bottom:2px;">${obj}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    let hypothesesHtml = '';
    if (brief.hypotheses && brief.hypotheses.length > 0) {
      hypothesesHtml = `
        <div style="margin-top:8px;">
          <div style="font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:hsl(var(--muted-foreground));margin-bottom:4px;">Working Hypotheses</div>
          <ul style="margin:0;padding-left:18px;font-size:0.85rem;color:hsl(var(--foreground));">
            ${brief.hypotheses.map(hyp => `<li style="margin-bottom:2px;">${hyp}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    let thinkerHtml = '';
    if (brief.thinker_context && Object.keys(brief.thinker_context).length > 0) {
      const tc = brief.thinker_context;
      thinkerHtml = `
        <div style="margin-top:8px;padding:8px 12px;border-radius:var(--radius-sm);background:hsl(var(--muted)/0.4);border-left:3px solid hsl(var(--primary));">
          <div style="font-size:0.75rem;font-weight:600;color:hsl(var(--primary));margin-bottom:2px;"><i data-lucide="compass" style="width:13px;height:13px;vertical-align:middle;margin-right:4px;"></i>Philosophical Sparring Lens: ${tc.thinker_name || tc.thinker_id || 'Thinker'} (${tc.archetype || 'Methodological Rigour'})</div>
          <div style="font-size:0.82rem;color:hsl(var(--foreground));">${tc.perspective || ''}</div>
          ${tc.unresolved_objections && tc.unresolved_objections.length > 0 ? `
            <div style="font-size:0.75rem;color:hsl(var(--muted-foreground));margin-top:4px;"><strong>Open Objections:</strong> ${tc.unresolved_objections.join('; ')}</div>
          ` : ''}
        </div>
      `;
    }

    let scopeCriteriaHtml = '';
    if ((brief.search_scope && brief.search_scope.length > 0) || (brief.selection_criteria && brief.selection_criteria.length > 0)) {
      scopeCriteriaHtml = `
        <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:12px;font-size:0.8rem;color:hsl(var(--muted-foreground));">
          ${brief.search_scope && brief.search_scope.length > 0 ? `<div><strong>Search Scope:</strong> ${brief.search_scope.join(', ')}</div>` : ''}
          ${brief.selection_criteria && brief.selection_criteria.length > 0 ? `<div><strong>Criteria:</strong> ${brief.selection_criteria.join('; ')}</div>` : ''}
        </div>
      `;
    }

    return `
      <div class="brief-mandate-card" style="padding:16px;border-radius:var(--radius-lg);background:hsl(var(--card));border:1px solid hsl(var(--border));box-shadow:0 4px 12px rgba(0,0,0,0.05);margin-bottom:12px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;border-bottom:1px solid hsl(var(--border));padding-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <i data-lucide="file-text" style="width:18px;height:18px;color:hsl(var(--primary));"></i>
            <span style="font-weight:600;font-size:0.95rem;color:hsl(var(--foreground));">Research Mandate & Brief</span>
            <span style="font-size:0.7rem;padding:2px 6px;border-radius:999px;background:hsl(var(--muted));color:hsl(var(--muted-foreground));">v${version}</span>
          </div>
          <span style="font-size:0.75rem;padding:2px 8px;border-radius:999px;font-weight:500;background:${isApproved ? 'hsl(142 76% 36% / 0.15)' : 'hsl(38 92% 50% / 0.15)'};color:${isApproved ? 'hsl(142 76% 36%)' : 'hsl(38 92% 40%)'};">
            ${isApproved ? 'Approved' : 'Pending Approval'}
          </span>
        </div>

        <div style="font-size:0.9rem;font-weight:500;color:hsl(var(--foreground));margin-bottom:6px;">
          <strong>Question:</strong> ${brief.research_question || topic}
        </div>

        ${objectivesHtml}
        ${hypothesesHtml}
        ${thinkerHtml}
        ${scopeCriteriaHtml}

        <div style="margin-top:14px;padding-top:10px;border-top:1px dashed hsl(var(--border));display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;">
          <div style="font-size:0.75rem;color:hsl(var(--muted-foreground));display:flex;align-items:center;gap:4px;">
            <i data-lucide="shield-check" style="width:14px;height:14px;color:hsl(var(--primary));"></i>
            Formal literature search & synthesis only begins upon explicit approval.
          </div>
          ${!isApproved ? `
            <button type="button" class="btn btn-primary" style="padding:6px 14px;font-size:0.82rem;font-weight:600;display:inline-flex;align-items:center;gap:6px;cursor:pointer;border-radius:var(--radius-md);" onclick="window.app.approveAndLaunchBrief('${briefId}', ${version}, '${safeTopic}')">
              <i data-lucide="check" style="width:14px;height:14px;"></i> Approve & Launch Deep Research
            </button>
          ` : `
            <span style="font-size:0.8rem;color:hsl(142 76% 36%);font-weight:600;"><i data-lucide="check-circle" style="width:14px;height:14px;vertical-align:middle;margin-right:4px;"></i>Approved (v${version})</span>
          `}
        </div>
      </div>
    `;
  }

  handlePipelineEvent(event, msgId) {
    const { node = '', update = {}, state = {} } = event || {};

    if (state && Object.keys(state).length > 0) {
      this.currentState = { ...(this.currentState || {}), ...state };
    }

    const msgContainer = document.getElementById(msgId);
    if (!msgContainer) return;

    const cotBody = msgContainer.querySelector('.cot-body');
    const contentBody = msgContainer.querySelector('.message-prose');

    if (node === 'clarification_gate') {
      const promptText = update.clarification_prompt || 'Clarification requested for this research scope:';
      const options = update.options || [];
      if (contentBody) {
        let optionsHtml = '';
        if (options.length > 0) {
          optionsHtml = `<div class="clarification-options" style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px;">` +
            options.map(opt => `<button type="button" class="proactive-pill" onclick="window.app.startResearch('${opt.replace(/'/g, "\\'")}', true, true)">${opt}</button>`).join('') +
            `</div>`;
        }
        contentBody.innerHTML = `
          <div class="clarification-card" style="padding:12px;border-radius:var(--radius-md);background:hsl(var(--muted)/0.5);border:1px solid hsl(var(--border));margin-bottom:8px;">
            <div style="font-weight:600;font-size:0.9rem;margin-bottom:6px;color:hsl(var(--foreground));"><i data-lucide="help-circle" style="width:15px;height:15px;vertical-align:middle;margin-right:6px;color:hsl(var(--primary));"></i>${promptText}</div>
            ${optionsHtml}
          </div>
          <div style="color:hsl(var(--muted-foreground));font-size:0.8rem;margin-top:4px;"><i data-lucide="loader" class="animate-spin" style="width:12px;height:12px;vertical-align:middle;margin-right:4px;"></i> Scribe is initiating broad academic search in parallel...</div>
        `;
        if (window.lucide) lucide.createIcons();
      }
      this.scrollToBottom();
      return;
    }

    if (node === 'approval_barrier') {
      const brief = update.brief || (state && state.brief) || {};
      const reason = update.barrier_reason || 'Formal research requires an explicit, approved Research Brief.';
      if (contentBody) {
        contentBody.innerHTML = this.renderBriefHtml(brief, reason);
        if (window.lucide) lucide.createIcons();
      }
      const cotAccordion = msgContainer.querySelector('.cot-accordion');
      if (cotAccordion) cotAccordion.style.display = 'none';
      this.scrollToBottom();
      return;
    }

    if (node === 'duplicate_execution_rejected') {
      const errorMsg = update.error || (state && state.error) || 'A research task is already active or completed for this brief version.';
      if (contentBody) {
        contentBody.innerHTML = `
          <div class="duplicate-execution-card" style="padding:14px;border-radius:var(--radius-md);background:hsl(var(--destructive)/0.08);border:1px solid hsl(var(--destructive)/0.3);margin-bottom:8px;">
            <div style="font-weight:600;font-size:0.92rem;margin-bottom:6px;color:hsl(var(--destructive));display:flex;align-items:center;gap:6px;">
              <i data-lucide="alert-triangle" style="width:16px;height:16px;"></i>
              <span>Execution Request Rejected</span>
            </div>
            <div style="font-size:0.875rem;color:hsl(var(--foreground));line-height:1.5;">
              ${errorMsg}
            </div>
          </div>
        `;
        if (window.lucide) lucide.createIcons();
      }
      const cotAccordion = msgContainer.querySelector('.cot-accordion');
      if (cotAccordion) cotAccordion.style.display = 'none';
      this.showToast(errorMsg, 'alert-triangle');
      this.scrollToBottom();
      return;
    }

    if (node === 'direct_chat') {
      const directAnswer = update.answer || state.direct_answer || '';
      if (contentBody) {
        contentBody.innerHTML = this.parseMarkdownWithWikilinks(directAnswer);
      }
      const cotAccordion = msgContainer.querySelector('.cot-accordion');
      if (cotAccordion) cotAccordion.style.display = 'none';
      if (state.follow_up_questions) {
        this.renderProactivePills(msgContainer, state.follow_up_questions);
      }
      this.renderMessageActions(msgContainer, this.activeTopic);
      this.scrollToBottom();
      return;
    }

    if (this.pipelineNodes.includes(node)) {
      if (this.stepperBar && (!this.stepperBar.children || this.stepperBar.children.length === 0)) {
        this.resetStepper();
      }
      this.updateStepperNode(node);
    }

    if (cotBody) {
      if (node === 'search') {
        cotBody.textContent += `[SEARCH] Querying academic indices for top ${this.scrapeTopN || 15} peer-reviewed papers.\n`;
      } else if (node === 'snowball') {
        cotBody.textContent += `[SNOWBALL] Expanded citation graph and forward reference seeds.\n`;
      } else if (node === 'scrape') {
        cotBody.textContent += `[READER] Fanning out concurrent scrape across top ${this.scrapeTopN || 15} candidate sources.\n`;
      } else if (node === 'prisma') {
        cotBody.textContent += `[PRISMA] Double-pass systematic screening & study eligibility ledger compiled.\n`;
      } else if (node === 'writer') {
        cotBody.textContent += `[SCRIBE] Drafted synthesis report (Attempt ${state.attempt || 1}).\n`;
      } else if (node === 'verifier') {
        cotBody.textContent += `[TRUTH GUARD] Verified claims against retrieved sources.\n`;
      } else if (node === 'critic') {
        cotBody.textContent += `[CRITIC] Rubric evaluated. Score: ${state.score || 0}/10.\n`;
      } else if (node === 'vault') {
        cotBody.textContent += `[VAULT] Persisted notes to Obsidian Markdown Vault & Indexed.\n`;
      } else if (node === 'manuscript') {
        cotBody.textContent += `[MANUSCRIPT] Structured manuscript instantiated with claim-evidence matrix (v${state.revision?.version || 1}).\n`;
      }
    }

    if (state.report) {
      this.renderReport(state.report);
      contentBody.innerHTML = this.parseMarkdownWithWikilinks(state.report);
    } else if (contentBody) {
      const count = this.scrapeTopN || 15;
      const stageMessages = {
        'clarification_gate': '🔍 Evaluating research mandate & topic scope...',
        'search': `🔍 Discovering top ${count} peer-reviewed papers across arXiv, Semantic Scholar & OpenAlex...`,
        'snowball': '🌐 Snowballing academic citation network & recommendations...',
        'scrape': `📖 Fanning out concurrent scrape across top ${count} primary sources...`,
        'prisma': '📑 PRISMA 2020: Screening title/abstracts and full text eligibility...',
        'writer': '✍️ Scribing comprehensive research synthesis...',
        'verifier': '⚖️ Scales of Ma\'at: Verifying factual claims against sources...',
        'critic': '🧐 Evaluating rigor and rubrics...',
        'manuscript': '📚 Scribing and structuring living academic manuscript...'
      };
      if (stageMessages[node]) {
        contentBody.innerHTML = `<span style="color:hsl(var(--primary));font-size:0.9rem;"><i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;vertical-align:middle;margin-right:6px;"></i> ${stageMessages[node]}</span>`;
        if (window.lucide) lucide.createIcons();
      }
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

    if (state.prisma_review) {
      this.renderPrismaPane(state.prisma_review);
    }

    if (state.manuscript || state.revision) {
      this.renderManuscriptPane(state.manuscript, state.revision, state.project_id);
    }

    if (node === 'manuscript' || node === 'follow_up' || node === 'complete') {
      this.completeStepper();
      if (state.follow_up_questions) {
        this.renderProactivePills(msgContainer, state.follow_up_questions);
      }
      this.renderMessageActions(msgContainer, state.topic || this.activeTopic);
    }
    this.scrollToBottom();
  }

  sendFollowup(query) {
    if (!this.currentState) {
      this.startResearch(query, false, true);
      return;
    }

    this.setGenerating(true);
    this.activeAbortController = new AbortController();
    const mode = this.activeMode || 'auto';

    const msgId = `msg_${Date.now()}`;
    const bubbleEl = this.createAssistantPlaceholder(msgId);

    const payload = {
      state: this.currentState,
      user_query: query,
      mode_override: mode
    };

    this._getHeaders().then(headers => {
      fetch(this._resolveUrl('/api/followup/stream'), {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        signal: this.activeAbortController.signal
      }).then(response => {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processStream = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            this.setGenerating(false);
            this.loadVaultNotes();
            return;
          }

          buffer += decoder.decode(value, { stream: true });

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
          if (err.name === 'AbortError') {
            console.log('Follow-up stream cancelled by user.');
            return;
          }
          console.error('Followup read error:', err);
          this.setGenerating(false);
          const bubbleEl = document.getElementById(msgId);
          if (bubbleEl) {
            const prose = bubbleEl.querySelector('.message-prose');
            if (prose && prose.textContent.includes('Consulting')) {
              prose.innerHTML = `<span style="color:hsl(var(--destructive));font-size:0.9rem;"><i data-lucide="alert-triangle" style="width:14px;height:14px;vertical-align:middle;margin-right:6px;"></i> Response stream interrupted.</span>`;
              if (window.lucide) lucide.createIcons();
            }
          }
          this.showToast('Follow-up stream interrupted', 'alert-triangle');
        });
      };

      processStream();
    }).catch(err => {
      if (err.name === 'AbortError') return;
      console.error('Followup fetch error:', err);
      this.setGenerating(false);
      const bubbleEl = document.getElementById(msgId);
      if (bubbleEl) {
        const prose = bubbleEl.querySelector('.message-prose');
        if (prose) {
          prose.innerHTML = `<span style="color:hsl(var(--destructive));font-size:0.9rem;"><i data-lucide="alert-triangle" style="width:14px;height:14px;vertical-align:middle;margin-right:6px;"></i> Unable to connect to assistant.</span>`;
          if (window.lucide) lucide.createIcons();
        }
      }
      this.showToast('Connection failed', 'alert-triangle');
    });
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
      contentBody.innerHTML = this.parseMarkdownWithWikilinks(payload.answer);
      if (payload.citations && payload.citations.length > 0) {
        this.renderCitations(msgContainer, payload.citations);
      }
      this.renderMessageActions(msgContainer, this.activeTopic || this.currentState?.topic);
      this.scrollToBottom();
    } else if (evType === 'report_expansion') {
      if (payload.updated_report) {
        this.currentState.report = payload.updated_report;
        this.renderReport(payload.updated_report);
      }
      if (contentBody && (payload.new_section || payload.updated_report)) {
        contentBody.innerHTML = this.parseMarkdownWithWikilinks(payload.new_section || payload.updated_report);
      }
      this.renderMessageActions(msgContainer, this.activeTopic || this.currentState?.topic);
      this.scrollToBottom();
    } else if (evType === 'followup_complete') {
      this.currentState.chat_turns = payload.chat_turns;
      this.currentState.conversation_summary = payload.conversation_summary;
      if (payload.topic) {
        this.currentState.topic = payload.topic;
        this.activeTopic = payload.topic;
        if (this.currentTopicDisplay) this.currentTopicDisplay.textContent = payload.topic;
      }
      if (payload.follow_up_questions) {
        this.renderProactivePills(msgContainer, payload.follow_up_questions);
      }
      this.renderMessageActions(msgContainer, this.activeTopic || this.currentState?.topic);
      this.scrollToBottom();
    }

  }

  scrollToBottom(force = false) {
    if (!this.chatFeed) return;
    if (force || !this.isUserScrolledUp) {
      this.chatFeed.scrollTop = this.chatFeed.scrollHeight;
      if (this.jumpToLatestBtn) this.jumpToLatestBtn.classList.add('hidden');
    } else if (this.isUserScrolledUp && this.jumpToLatestBtn) {
      this.jumpToLatestBtn.classList.remove('hidden');
    }
  }

  renderMessageActions(containerEl, topic) {
    if (!containerEl) return;
    const bubble = containerEl.querySelector('.chat-bubble');
    if (!bubble) return;

    let actionsBar = bubble.querySelector('.message-actions-bar');
    if (!actionsBar) {
      actionsBar = document.createElement('div');
      actionsBar.className = 'message-actions-bar';
      bubble.appendChild(actionsBar);
    }
    const cleanTopic = (topic || this.activeTopic || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    actionsBar.innerHTML = `
      <button class="msg-action-btn primary" onclick="window.app.triggerDirectResearch('${cleanTopic}')" title="Conduct comprehensive 8-agent literature synthesis on this topic">
        <i data-lucide="microscope" style="width:12px;height:12px;"></i>
        <span>Deep Research</span>
      </button>
      <button class="msg-action-btn" onclick="window.app.switchArtifactTab('prisma')" title="View PRISMA systematic review flow & screening ledger">
        <i data-lucide="filter" style="width:12px;height:12px;"></i>
        <span>PRISMA</span>
      </button>
      <button class="msg-action-btn" onclick="window.app.switchArtifactTab('manuscript')" title="View structured academic manuscript draft">
        <i data-lucide="book-open" style="width:12px;height:12px;"></i>
        <span>Manuscript</span>
      </button>
      <button class="msg-action-btn" onclick="window.app.promptIdeaCapture('${cleanTopic}')" title="Capture conversational observation as a tentative research idea">
        <i data-lucide="sparkles" style="width:12px;height:12px;"></i>
        <span>Idea</span>
      </button>
      <button class="msg-action-btn" onclick="window.app.copyMessageText(this)" title="Copy message text">
        <i data-lucide="copy" style="width:12px;height:12px;"></i>
        <span>Copy</span>
      </button>
      <button class="msg-action-btn" onclick="window.app.switchArtifactTab('report')" title="View report in side pane">
        <i data-lucide="file-text" style="width:12px;height:12px;"></i>
        <span>Report</span>
      </button>
      <button class="msg-action-btn" onclick="window.app.switchArtifactTab('truth')" title="View fact verification audit">
        <i data-lucide="scale" style="width:12px;height:12px;"></i>
        <span>Scales</span>
      </button>
    `;
    if (window.lucide) lucide.createIcons();
  }

  promptIdeaCapture(defaultTitle = '') {
    const title = prompt('Capture Tentative Idea — Enter a working title:', defaultTitle || this.activeTopic || 'New Research Idea');
    if (!title) return;
    const hyp = prompt('Enter the core testable hypothesis:', `Investigating whether ${title.toLowerCase()} presents valid empirical mechanisms.`);
    if (!hyp) return;
    this.captureTentativeIdea(title, hyp, `Formulated from conversational dialogue regarding ${title}`);
  }

  copyMessageText(btnEl) {
    const bubble = btnEl.closest('.chat-bubble');
    const prose = bubble?.querySelector('.message-prose') || bubble?.querySelector('.prose');
    if (!prose) return;
    const text = prose.innerText;
    navigator.clipboard.writeText(text).then(() => {
      this.showToast('Copied message to clipboard!');
      const span = btnEl.querySelector('span');
      if (span) {
        const orig = span.textContent;
        span.textContent = 'Copied!';
        setTimeout(() => { span.textContent = orig; }, 2000);
      }
    }).catch(() => {
      this.showToast('Failed to copy', 'alert-circle');
    });
  }

  triggerDirectResearch(topic) {
    if (this.isGenerating) return;
    this.setMode('deep_research');
    const query = topic || this.activeTopic || (this.currentState && this.currentState.topic) || 'Current research objective';
    this.startResearch(query, true, true);
  }

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
    this.scrollToBottom(true);
  }

  appendAssistantMessage(text) {
    // Card renderer for the unified /api/chat/stream events (Phases 1-3).
    const row = document.createElement('div');
    row.className = 'chat-message-row assistant';
    row.innerHTML = `
      <div class="chat-avatar">
        <img src="/assets/thoth_bust.jpg" alt="Thoth">
      </div>
      <div class="chat-bubble">
        <div class="message-prose prose">${marked.parse(text || '')}</div>
      </div>
    `;
    this.chatFeed.appendChild(row);
    if (window.ThothAnimations) window.ThothAnimations.animateNewMessage(row);
    this.scrollToBottom(true);
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
    if (this.isResearchDirective(questionText)) {
      this.startResearch(questionText, true, true);
    } else {
      this.chatInput.value = questionText;
      this.handleChatSend();
    }
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

  showToast(message, icon = 'check-circle') {
    let container = document.getElementById('thothToastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'thothToastContainer';
      container.className = 'thoth-toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'thoth-toast';
    toast.innerHTML = `<i data-lucide="${icon}" style="width:14px;height:14px;color:#c99a6b;"></i> <span>${message}</span>`;
    container.appendChild(toast);
    if (window.lucide) lucide.createIcons();

    setTimeout(() => {
      toast.classList.add('hiding');
      setTimeout(() => toast.remove(), 300);
    }, 2800);
  }

  copyReportMarkdown() {
    const report = this.currentState?.report;
    if (!report) {
      this.showToast('No report content available to copy', 'alert-circle');
      return;
    }
    navigator.clipboard.writeText(report).then(() => {
      this.showToast('Report Markdown copied to clipboard!');
    }).catch(() => {
      this.showToast('Failed to copy to clipboard', 'alert-circle');
    });
  }

  downloadReportMarkdown() {
    const report = this.currentState?.report;
    if (!report) {
      this.showToast('No report content available to download', 'alert-circle');
      return;
    }
    const topic = this.currentState?.topic || 'thoth_research';
    const slug = topic.toLowerCase().replace(/[^a-z0-9]+/g, '_').substring(0, 35);
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `thoth_report_${slug}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    this.showToast(`Downloaded thoth_report_${slug}.md`);
  }

  printReport() {
    const report = this.currentState?.report;
    if (!report) {
      this.showToast('No report content available to print', 'alert-circle');
      return;
    }
    window.print();
  }

  copyBibtex(idx) {
    const sources = this.currentState?.cumulative_sources || [];
    const s = sources[idx];
    if (!s) return;

    const key = (s.authors?.[0]?.split(' ')?.[0] || 'Author') + (s.year || new Date().getFullYear()) + (s.title?.split(' ')?.[0] || 'Paper');
    const cleanKey = key.replace(/[^a-zA-Z0-9]/g, '');
    const bibtex = `@article{${cleanKey},
  title={${s.title || 'Untitled'}},
  author={${(s.authors && s.authors.length) ? s.authors.join(' and ') : 'Thoth Research'}},
  url={${s.url || ''}},
  doi={${s.doi || ''}},
  year={${s.year || new Date().getFullYear()}},
  journal={${s.source_api ? 'Discovered via ' + s.source_api : 'Academic Literature'}}
}`;

    navigator.clipboard.writeText(bibtex).then(() => {
      this.showToast(`Copied BibTeX for: ${(s.title || '').substring(0, 30)}...`);
    });
  }

  copyApaCitation(idx) {
    const sources = this.currentState?.cumulative_sources || [];
    const s = sources[idx];
    if (!s) return;

    const authorStr = (s.authors && s.authors.length) ? s.authors.join(', ') : 'Unknown Author';
    const yearStr = s.year || new Date().getFullYear();
    const apa = `${authorStr} (${yearStr}). ${s.title || 'Untitled'}. Retrieved from ${s.url || ''}`;

    navigator.clipboard.writeText(apa).then(() => {
      this.showToast('Copied APA citation to clipboard!');
    });
  }

  parseMarkdownWithWikilinks(text) {
    if (!text) return '';
    // Replace [[note_or_source_id]] with interactive badge
    const withBadges = text.replace(/\[\[([a-zA-Z0-9_\-]+)\]\]/g, (match, p1) => {
      return `<a href="javascript:void(0)" class="wikilink-badge" onclick="window.app.handleWikilinkClick('${p1}')"><i data-lucide="file-text" style="width:10px;height:10px;"></i> [[${p1}]]</a>`;
    });
    return marked.parse(withBadges);
  }

  handleWikilinkClick(id) {
    if (id.startsWith('src-')) {
      this.switchArtifactTab('sources');
      this.showToast(`Inspecting Source: ${id}`);
    } else {
      this.openNote(id);
    }
  }

  renderReport(reportMarkdown) {
    if (!this.artifactReportPane) return;

    const words = reportMarkdown ? reportMarkdown.trim().split(/\s+/).length : 0;
    const readingTimeMin = Math.max(1, Math.ceil(words / 200));

    this.artifactReportPane.innerHTML = `
      <div class="report-export-toolbar">
        <div class="export-meta-badge">
          <i data-lucide="book-open" style="width:13px;height:13px;color:#c99a6b;"></i>
          <span>${words.toLocaleString()} words · ~${readingTimeMin} min read</span>
        </div>
        <div class="export-buttons-group">
          <button class="export-btn" onclick="window.app.copyReportMarkdown()" title="Copy Markdown to Clipboard">
            <i data-lucide="copy" style="width:12px;height:12px;"></i> Copy .md
          </button>
          <button class="export-btn" onclick="window.app.downloadReportMarkdown()" title="Download Markdown File">
            <i data-lucide="download" style="width:12px;height:12px;"></i> Download
          </button>
          <button class="export-btn" onclick="window.app.printReport()" title="Print / Export PDF">
            <i data-lucide="printer" style="width:12px;height:12px;"></i> Export PDF
          </button>
        </div>
      </div>
      <div class="prose">
        ${this.parseMarkdownWithWikilinks(reportMarkdown)}
      </div>
    `;
    if (window.lucide) lucide.createIcons();
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
      <div class="source-card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <span style="font-weight:700;font-size:0.85rem;color:#fff;">${s.title || 'Source ' + (idx + 1)}</span>
          <span class="mono" style="font-size:0.7rem;color:hsl(var(--primary));background:hsl(var(--card));padding:2px 6px;border-radius:4px;white-space:nowrap;">${s.source_api || 'web'}</span>
        </div>
        <div style="font-size:0.75rem;color:hsl(var(--muted-foreground));line-height:1.4;">${s.snippet || s.abstract || '(No abstract provided)'}</div>
        <div class="source-actions-row">
          <a href="${s.url}" target="_blank" class="citation-btn" style="text-decoration:none;">
            <i data-lucide="external-link" style="width:11px;height:11px;"></i> Open URL
          </a>
          <button class="citation-btn" onclick="window.app.copyBibtex(${idx})">
            <i data-lucide="file-code" style="width:11px;height:11px;"></i> BibTeX
          </button>
          <button class="citation-btn" onclick="window.app.copyApaCitation(${idx})">
            <i data-lucide="quote" style="width:11px;height:11px;"></i> APA
          </button>
        </div>
      </div>
    `).join('');

    this.artifactSourcesPane.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:12px;">
        ${items}
      </div>
    `;
    if (window.lucide) lucide.createIcons();
  }

  renderPrismaPane(prismaData) {
    if (!this.artifactPrismaPane) return;
    if (!prismaData) {
      this.artifactPrismaPane.innerHTML = `<p style="color:hsl(var(--muted-foreground));font-size:0.85rem;">Systematic PRISMA 2020 review flow & screening ledger will appear here.</p>`;
      return;
    }

    const counts = prismaData.flow_counts || {};
    const decisions = prismaData.decisions || this.currentState?.screening_decisions || [];
    const evMatrix = prismaData.evidence_matrix || this.currentState?.evidence_matrix || {};
    const studies = evMatrix.included_studies || [];
    const contradictions = evMatrix.dialectical_contradictions || [];

    const totalIdentified = counts.total_identified || 0;
    const screened = counts.records_screened || 0;
    const excludedTA = counts.records_excluded_title_abstract || 0;
    const retrieved = counts.reports_sought_for_retrieval || 0;
    const assessedFT = counts.reports_assessed_for_eligibility || 0;
    const excludedFT = counts.reports_excluded_full_text || 0;
    const includedReports = counts.included_reports || 0;
    const includedStudies = counts.included_studies || studies.length;

    let decisionsHtml = '';
    if (decisions.length > 0) {
      decisionsHtml = `
        <div style="margin-top:16px;">
          <h4 style="font-size:0.85rem;font-weight:600;margin-bottom:8px;color:hsl(var(--foreground));">Screening Ledger (${decisions.length} Decisions)</h4>
          <div style="max-height:280px;overflow-y:auto;border:1px solid hsl(var(--border));border-radius:var(--radius-sm);">
            <table class="truth-guard-table" style="margin:0;font-size:0.75rem;">
              <thead>
                <tr>
                  <th>Paper / Report</th>
                  <th>Stage</th>
                  <th>Disposition</th>
                  <th>Rationale</th>
                </tr>
              </thead>
              <tbody>
                ${decisions.map(d => {
                  const disp = d.disposition || 'UNRESOLVED';
                  const dispColor = disp === 'INCLUDED' ? '#10b981' : (disp === 'EXCLUDED' ? '#ef4444' : '#f59e0b');
                  return `
                    <tr>
                      <td style="font-weight:500;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${d.title || ''}">${d.title || 'Untitled'}</td>
                      <td><span style="font-size:0.7rem;color:hsl(var(--muted-foreground));">${d.stage === 'TITLE_ABSTRACT' ? 'Title/Abs' : 'Full Text'}</span></td>
                      <td><span style="display:inline-block;padding:2px 6px;border-radius:4px;font-weight:600;font-size:0.7rem;background:${dispColor}20;color:${dispColor};border:1px solid ${dispColor}40;">${disp}</span></td>
                      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${d.rationale || ''}">${d.exclusion_reason ? `<strong>[${d.exclusion_reason}]</strong> ` : ''}${d.rationale || 'N/A'}</td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    let contradictionsHtml = '';
    if (contradictions.length > 0) {
      contradictionsHtml = `
        <div style="margin-top:16px;padding:12px;border-radius:var(--radius-sm);background:hsl(var(--destructive)/0.08);border:1px solid hsl(var(--destructive)/0.3);">
          <div style="font-weight:600;font-size:0.82rem;color:hsl(var(--destructive));margin-bottom:6px;display:flex;align-items:center;gap:6px;">
            <i data-lucide="alert-circle" style="width:14px;height:14px;"></i>
            <span>Dialectical Contradictions & Counter-Evidence (${contradictions.length})</span>
          </div>
          ${contradictions.map(c => `
            <div style="font-size:0.75rem;margin-bottom:6px;line-height:1.4;">
              <span style="font-weight:600;color:hsl(var(--foreground));">Hypothesis:</span> ${c.hypothesis || 'Core claim'}<br>
              <span style="color:#ef4444;font-weight:500;">Opposing Finding:</span> ${c.opposing_finding || 'Contradicting empirical outcome'}<br>
              <span style="color:hsl(var(--muted-foreground));">Dialectic Resolution:</span> ${c.synthesis_notes || 'Requires qualification.'}
            </div>
          `).join('')}
        </div>
      `;
    }

    this.artifactPrismaPane.innerHTML = `
      <div style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <h3 class="serif" style="color:hsl(var(--primary));margin:0;font-size:1rem;">PRISMA 2020 Systematic Review</h3>
          <span class="mono" style="font-size:0.7rem;color:hsl(var(--primary));background:hsl(var(--primary)/0.1);padding:2px 8px;border-radius:4px;">
            ID: ${prismaData.review_id || 'active'}
          </span>
        </div>
        <p style="font-size:0.78rem;color:hsl(var(--muted-foreground));margin-top:4px;">
          Full systematic review accounting & screening flow tracking study eligibility.
        </p>
      </div>

      <div style="display:grid;grid-template-columns:repeat(2, 1fr);gap:8px;margin-bottom:12px;">
        <div style="background:hsl(var(--card));padding:10px;border-radius:var(--radius-sm);border:1px solid hsl(var(--border));text-align:center;">
          <div style="font-size:1.2rem;font-weight:700;color:hsl(var(--primary));">${totalIdentified}</div>
          <div style="font-size:0.7rem;color:hsl(var(--muted-foreground));text-transform:uppercase;letter-spacing:0.05em;">Identified Records</div>
        </div>
        <div style="background:hsl(var(--card));padding:10px;border-radius:var(--radius-sm);border:1px solid hsl(var(--border));text-align:center;">
          <div style="font-size:1.2rem;font-weight:700;color:#f59e0b;">${screened} (${excludedTA} Excl)</div>
          <div style="font-size:0.7rem;color:hsl(var(--muted-foreground));text-transform:uppercase;letter-spacing:0.05em;">Title/Abstract Screened</div>
        </div>
        <div style="background:hsl(var(--card));padding:10px;border-radius:var(--radius-sm);border:1px solid hsl(var(--border));text-align:center;">
          <div style="font-size:1.2rem;font-weight:700;color:#3b82f6;">${assessedFT} (${excludedFT} Excl)</div>
          <div style="font-size:0.7rem;color:hsl(var(--muted-foreground));text-transform:uppercase;letter-spacing:0.05em;">Full Text Assessed</div>
        </div>
        <div style="background:hsl(var(--card));padding:10px;border-radius:var(--radius-sm);border:1px solid #10b98140;text-align:center;background:#10b98110;">
          <div style="font-size:1.2rem;font-weight:700;color:#10b981;">${includedReports} Reports (${includedStudies} Studies)</div>
          <div style="font-size:0.7rem;color:#10b981;text-transform:uppercase;letter-spacing:0.05em;">Included in Synthesis</div>
        </div>
      </div>

      ${decisionsHtml}
      ${contradictionsHtml}
    `;
    if (window.lucide) lucide.createIcons();
  }

  renderManuscriptPane(msData, revData, projectId) {
    if (!this.artifactManuscriptPane) return;
    if (!msData && !revData) {
      this.artifactManuscriptPane.innerHTML = `<p style="color:hsl(var(--muted-foreground));font-size:0.85rem;">Living structured academic manuscript with claim-level evidence matrices.</p>`;
      return;
    }

    const manuscript = msData || {};
    const revision = revData || this.currentState?.revision || {};
    const mid = manuscript.manuscript_id || this.currentState?.manuscript_id || '';
    const pid = projectId || manuscript.project_id || this.currentState?.project_id || '';
    const version = revision.version || manuscript.current_version || 1;
    const title = revision.title || manuscript.title || 'Academic Manuscript Draft';
    const sections = revision.sections || {};
    const claims = revision.claims || [];

    const sectionEntries = Object.entries(sections).sort((a, b) => (a[1].order || 0) - (b[1].order || 0));

    let sectionsHtml = sectionEntries.map(([secKey, sec]) => `
      <details style="margin-bottom:8px;border:1px solid hsl(var(--border));border-radius:var(--radius-sm);background:hsl(var(--card));" open>
        <summary style="padding:8px 12px;font-weight:600;font-size:0.82rem;cursor:pointer;color:hsl(var(--primary));display:flex;justify-content:space-between;align-items:center;">
          <span>${sec.heading || secKey}</span>
          <span style="font-size:0.7rem;color:hsl(var(--muted-foreground));text-transform:uppercase;">${sec.section_type || 'standard'}</span>
        </summary>
        <div style="padding:10px 12px;font-size:0.8rem;line-height:1.5;color:hsl(var(--foreground));border-top:1px solid hsl(var(--border));white-space:pre-wrap;">${sec.content || ''}</div>
      </details>
    `).join('');

    let claimsHtml = '';
    if (claims.length > 0) {
      claimsHtml = `
        <div style="margin-top:16px;">
          <h4 style="font-size:0.85rem;font-weight:600;margin-bottom:8px;color:hsl(var(--foreground));">Claim-to-Evidence Matrix (${claims.length} Claims)</h4>
          <div style="max-height:240px;overflow-y:auto;border:1px solid hsl(var(--border));border-radius:var(--radius-sm);">
            <table class="truth-guard-table" style="margin:0;font-size:0.75rem;">
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Sources</th>
                </tr>
              </thead>
              <tbody>
                ${claims.map(c => {
                  const status = c.evidence_status || 'UNVERIFIED';
                  const stColor = status === 'SUPPORTED' ? '#10b981' : (status === 'QUALIFIED' ? '#3b82f6' : (status === 'CHALLENGED' ? '#ef4444' : '#94a3b8'));
                  const supp = (c.supporting_sources || []).map(s => typeof s === 'string' ? s : (s.title || s.url || 'Source')).join(', ') || 'None';
                  return `
                    <tr>
                      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${c.claim_text || ''}">${c.claim_text || ''}</td>
                      <td><span style="display:inline-block;padding:2px 6px;border-radius:4px;font-weight:600;font-size:0.7rem;background:${stColor}20;color:${stColor};border:1px solid ${stColor}40;">${status}</span></td>
                      <td class="mono">${Math.round((c.confidence || 0) * 100)}%</td>
                      <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${supp}">${supp}</td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    this.artifactManuscriptPane.innerHTML = `
      <div style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <h3 class="serif" style="color:hsl(var(--primary));margin:0;font-size:0.95rem;line-height:1.3;">${title}</h3>
          <span class="mono" style="font-size:0.7rem;color:#10b981;background:#10b98115;border:1px solid #10b98140;padding:2px 6px;border-radius:4px;white-space:nowrap;">
            v${version}
          </span>
        </div>
        <p style="font-size:0.75rem;color:hsl(var(--muted-foreground));margin-top:4px;">
          Project: <span class="mono">${pid || 'Default'}</span> · Manuscript: <span class="mono">${mid}</span>
        </p>
      </div>

      <div class="report-export-toolbar" style="margin-bottom:12px;">
        <span style="font-size:0.75rem;color:hsl(var(--muted-foreground));font-weight:500;">Export Draft:</span>
        <div class="export-buttons-group">
          <button class="export-btn" onclick="window.app.exportManuscript('${mid}', 'markdown', ${version}, '${pid}')" title="Export Academic Markdown">
            <i data-lucide="file-text" style="width:11px;height:11px;"></i> .md
          </button>
          <button class="export-btn" onclick="window.app.exportManuscript('${mid}', 'latex', ${version}, '${pid}')" title="Export LaTeX Source">
            <i data-lucide="code" style="width:11px;height:11px;"></i> LaTeX
          </button>
          <button class="export-btn" onclick="window.app.exportManuscript('${mid}', 'bibtex', ${version}, '${pid}')" title="Export BibTeX Bibliography">
            <i data-lucide="file-code" style="width:11px;height:11px;"></i> BibTeX
          </button>
          <button class="export-btn" onclick="window.app.exportManuscript('${mid}', 'pdf', ${version}, '${pid}')" title="Export Academic PDF">
            <i data-lucide="printer" style="width:11px;height:11px;"></i> PDF
          </button>
        </div>
      </div>

      <div style="margin-bottom:8px;">
        <h4 style="font-size:0.85rem;font-weight:600;margin-bottom:8px;color:hsl(var(--foreground));">Manuscript Sections</h4>
        ${sectionsHtml || '<p style="color:hsl(var(--muted-foreground));font-size:0.8rem;">No sections drafted yet.</p>'}
      </div>

      ${claimsHtml}
    `;
    if (window.lucide) lucide.createIcons();
  }

  async exportManuscript(manuscriptId, formatType, version, projectId) {
    if (!manuscriptId) {
      this.showToast('No active manuscript to export', 'alert-triangle');
      return;
    }
    this.showToast(`Generating ${formatType.toUpperCase()} export...`, 'loader');
    try {
      const url = `/api/workspace/manuscripts/${encodeURIComponent(manuscriptId)}/export`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          format: formatType,
          version: version || 1,
          engine: 'typst'
        })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Export failed with status ${res.status}`);
      }
      const data = await res.json();
      const exp = data.export || {};
      const content = exp.content || '';
      const filename = exp.filename || `manuscript_${manuscriptId}_v${version}.${formatType === 'markdown' ? 'md' : (formatType === 'latex' ? 'tex' : (formatType === 'bibtex' ? 'bib' : 'pdf'))}`;

      if (formatType === 'pdf' && exp.binary_base64) {
        const byteCharacters = atob(exp.binary_base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'application/pdf' });
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(blobUrl);
      } else {
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(blobUrl);
      }
      this.showToast(`${formatType.toUpperCase()} export ready: ${filename}`, 'check');
    } catch (err) {
      this.showToast(`Export error: ${err.message}`, 'alert-triangle');
    }
  }

  async captureTentativeIdea(title, hypothesis, description = '') {
    try {
      const res = await fetch('/api/ideas/tentative', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title,
          hypothesis: hypothesis,
          description: description,
          session_id: this.currentState?.session_id || ''
        })
      });
      const data = await res.json();
      if (data.success && data.idea) {
        this.showToast(`Tentative idea captured: "${data.idea.title}"`, 'sparkles');
        return data.idea;
      }
    } catch (err) {
      this.showToast(`Error capturing idea: ${err.message}`, 'alert-triangle');
    }
    return null;
  }

  async promoteIdeaToResearch(ideaId) {
    try {
      const res = await fetch(`/api/ideas/${encodeURIComponent(ideaId)}/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true })
      });
      const data = await res.json();
      if (data.success && data.idea) {
        this.showToast(`Idea promoted to persistent research!`, 'check');
        this.startResearch(data.idea.hypothesis || data.idea.title, true, false);
      } else {
        throw new Error(data.message || 'Promotion failed');
      }
    } catch (err) {
      this.showToast(`Promotion error: ${err.message}`, 'alert-triangle');
    }
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
    this._getHeaders().then(headers => {
      fetch(this._resolveUrl('/api/vault/notes'), { headers })
        .then(res => res.json())
        .then(data => {
          this.vaultNotes = data.notes || [];
          this.renderVaultNotesList(this.vaultNotes);
          const countEl = document.getElementById('vaultCountBadge');
          if (countEl) countEl.textContent = `${this.vaultNotes.length} notes`;
        })
        .catch(e => console.error('Failed to load vault notes:', e));
    });
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
    this._getHeaders().then(headers => {
      fetch(this._resolveUrl(`/api/vault/note/${noteId}`), { headers })
        .then(res => res.json())
        .then(note => {
          if (this.modalTitle) this.modalTitle.textContent = note.id;
          if (this.modalBody) this.modalBody.innerHTML = marked.parse(note.content || '(Empty Note)');
          if (this.noteModal) this.noteModal.classList.remove('hidden');
        })
        .catch(e => console.error('Failed to fetch note:', e));
    });
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
