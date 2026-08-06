<template>
  <div class="review-workspace-page">
    <div class="dashboard-hero card compact-header-card">
      <div>
        <div class="dashboard-kicker">Trading Journal</div>
        <h1 class="dashboard-title">Review Workspace</h1>
        <p class="dashboard-subtitle">先处理待办，再完成日复盘：Summary → Trades → Daily → Positions。</p>
      </div>
    </div>

    <section class="card tv-tabbed-panel tv-tabbed-panel-compact">
      <div class="tv-panel-tabs">
        <button :class="['tv-subtab', { active: journalTab === 'pretrade' }]" @click="openPretradeTab">Pre-Trade Plan</button>
        <button :class="['tv-subtab', { active: journalTab === 'workspace' }]" @click="openWorkspaceTab">Review Workspace</button>
        <button :class="['tv-subtab', { active: journalTab === 'analytics' }]" @click="openAnalyticsTab">Analytics</button>
      </div>
    </section>

    <div v-if="actionNotice" class="action-toast" role="status" aria-live="polite">{{ actionNotice }}</div>

    <template v-if="journalTab === 'workspace'">
    <div class="card workspace-review-cluster">
    <section class="card workspace-summary-card">
      <div class="journal-form-grid workspace-summary-grid">
        <div class="stat-pill queue-date-pill" :title="fieldHint('queue_date')">
          <div class="stat-label">Date</div>
          <input class="queue-date-input" v-model="queueDate" type="date" @change="loadQueue" @click="openDatePicker" @focus="openDatePicker" />
        </div>
        <div class="stat-pill"><div class="stat-label">Closed Trades</div><div class="stat-value medium">{{ queue.summary.closed_trade_count || 0 }}</div></div>
        <div class="stat-pill"><div class="stat-label">Open Positions</div><div class="stat-value medium">{{ queue.summary.open_position_count || 0 }}</div></div>
        <div class="stat-pill"><div class="stat-label">Daily Review</div><div class="stat-value medium">{{ queue.summary.daily_review_completed ? 'Done' : 'Pending' }}</div></div>
        <div class="stat-pill"><div class="stat-label">Completion</div><div class="stat-value medium">{{ completionRate }}%</div><div class="muted-copy completion-summary-line">{{ completionSummary }}</div></div>
        <button @click="focusFirstPending" class="secondary" :disabled="!queuePretradeReady">Start Review</button>
        <div class="muted-copy summary-pretrade-note" v-if="!queuePretradeReady">{{ queuePretradeMessage }}</div>
      </div>
    </section>

    <section class="card workspace-primary-card" ref="tradeSectionRef">
      <div class="section-title">Trade Review Cards</div>
      <div v-if="!queue.closed_trades?.length" class="empty-row">No closed trades for this day.</div>
      <div class="trade-card-grid">
        <div v-for="card in queue.closed_trades" :key="card.trade_group_id" class="journal-entry-card trade-review-card">
          <div class="trade-review-head">
            <div class="review-head-main">
              <div class="review-title-row"><strong>{{ card.symbol }}</strong> <span :class="['review-pnl-pill', card.realized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative']">{{ card.realized_pnl }}</span> <span :class="['badge', tradeStatusClass(card.status)]">{{ card.status }}</span></div>
              <div class="summary-chip-row">
                <span class="badge" :class="card.realized_pnl >= 0 ? 'badge-profit' : 'badge-loss'">R: {{ card.trade_review?.realized_r ?? '-' }}</span>
                <span class="badge">Mistake: {{ card.mistake_tags?.[0] || 'No mistake' }}</span>
                <span class="badge">Rule: {{ card.broke_stop_rule ? 'Stop rule' : 'None' }}</span>
                <span class="badge">Setup: {{ card.setup_name || '-' }} · Grade: {{ card.grade || '-' }}</span>
              </div>
              <div class="muted-copy">Hold {{ card.hold_minutes || '-' }}m · Exec {{ card.executions_count }} · Shots {{ card.screenshots_count }}</div>
              <div class="chip-wrap" v-if="(card.mistake_tags || []).length">
                <span v-for="tag in card.mistake_tags" :key="`mist-${card.trade_group_id}-${tag}`" class="badge badge-loss">{{ tag }}</span>
              </div>
              <div class="muted-copy">Plan vs Exec: entry {{ card.planned_entry ?? '-' }} → {{ card.actual_entry ?? '-' }} · stop {{ card.planned_stop ?? '-' }} · target {{ card.planned_target ?? '-' }}</div>
              <div class="chip-wrap">
                <span v-if="card.late_entry" class="badge badge-loss">Late entry</span>
                <span v-if="card.broke_stop_rule" class="badge badge-loss">Broke stop rule</span>
                <span class="badge">Setup match: {{ card.setup_match == null ? '-' : (card.setup_match ? 'Yes' : 'No') }}</span>
              </div>
              <div class="chip-wrap">
                <span v-if="!(card.missing_items || []).length" class="badge badge-profit">Review complete</span>
                <span v-for="item in card.missing_items || []" :key="`miss-${card.trade_group_id}-${item}`" :class="['badge', missingItemBadgeClass(item)]">Missing {{ item }}</span>
              </div>
            </div>
            <div class="trade-review-progress">
              <div class="progress-bar"><div class="progress-fill" :style="{ width: `${card.review_completeness || 0}%` }"></div></div>
              <div class="muted-copy trade-review-percent">{{ card.review_completeness || 0 }}%</div>
            </div>
          </div>
          <div class="trade-review-actions">
            <button class="secondary small-btn" @click="toggleCard(card.trade_group_id)">
              {{ expandedCards.includes(card.trade_group_id) ? 'Close' : 'Edit Review' }}
            </button>
          </div>

          <div v-if="expandedCards.includes(card.trade_group_id)" class="accordion-body compact-trade-body">
            <div class="journal-form-grid trade-review-form-grid">
              <label :title="fieldHint('setup')"><span>Setup</span>
                <select v-model="tradeReviewForms[card.trade_group_id].setup">
                  <option :value="null">-</option>
                  <option v-for="item in setupTags" :key="item.id" :value="item.id">{{ item.name }}</option>
                </select>
              </label>
              <label :title="fieldHint('linked_snapshot')"><span>Linked Snapshot</span>
                <select v-model.number="tradeReviewForms[card.trade_group_id].selected_snapshot">
                  <option :value="null">-</option>
                  <option v-for="opt in card.snapshot_options || []" :key="opt.id" :value="Number(opt.id)">
                    #{{ opt.id }} · {{ opt.symbol }} · {{ opt.setup_type }} · {{ opt.timeframe }} · Entry {{ opt.planned_entry ?? '-' }} · Risk {{ opt.planned_risk_r ?? '-' }}R
                  </option>
                </select>
              </label>
              <label :title="fieldHint('grade')"><span>Grade</span><select v-model="tradeReviewForms[card.trade_group_id].final_grade"><option value="">-</option><option>A</option><option>B</option><option>C</option><option>D</option></select></label>
              <label :title="fieldHint('plan_follow_take_again')"><span>Plan follow</span><select v-model="tradeReviewForms[card.trade_group_id].plan_follow_take_again"><option value="">-</option><option value="yes">Yes</option><option value="no">No</option><option value="with_changes">With changes</option></select></label>
              <label :title="fieldHint('realized_r')"><span>R multiple</span><input type="number" step="0.1" v-model.number="tradeReviewForms[card.trade_group_id].realized_r" /></label>
              <label :title="fieldHint('primary_mistake_type')"><span>Mistake type</span><select v-model="tradeReviewForms[card.trade_group_id].primary_mistake_type"><option value="none">No mistake</option><option value="discipline">FOMO</option><option value="risk">Risk</option><option value="execution">Execution</option></select></label>
              <label :title="fieldHint('mistake_severity')"><span>Mistake severity</span><select v-model="tradeReviewForms[card.trade_group_id].mistake_severity"><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select></label>
              <label :title="fieldHint('rule_violation_type')"><span>Rule violation type</span><select v-model="tradeReviewForms[card.trade_group_id].rule_violation_type"><option value="none">none</option><option value="entry_rule">entry_rule</option><option value="risk_rule">risk_rule</option><option value="exit_rule">exit_rule</option><option value="size_rule">size_rule</option></select></label>
            </div>
            <div class="trade-review-text-grid">
              <label :title="fieldHint('thesis')"><span>Thesis</span><textarea v-model="tradeReviewForms[card.trade_group_id].thesis" rows="2"></textarea></label>
              <label :title="fieldHint('next_time_rule')"><span>Next time rule</span><textarea v-model="tradeReviewForms[card.trade_group_id].what_to_improve" rows="2" placeholder="If [X happens] → I will [Y]"></textarea></label>
            </div>

            <div :title="fieldHint('mistake_tags')"><span>Mistake Tags</span><div class="chip-wrap">
              <button v-for="tag in mistakeTags" :key="tag.id" type="button" :class="['trade-option-chip', { active: (tradeReviewForms[card.trade_group_id].mistake_tags || []).includes(tag.id) }]" @click="toggleTradeMistakeTag(card.trade_group_id, tag.id)">{{ tag.name }}</button>
            </div></div>
            <label :title="fieldHint('screenshots')">
              <span>Screenshots</span>
              <div class="helper-row">
                <input type="file" accept="image/*" multiple @change="uploadTradeScreenshots(card.trade_group_id, $event)" />
                <span class="muted-copy" v-if="uploadingTrade === card.trade_group_id">Uploading...</span>
              </div>
            </label>
            <div v-if="(tradeReviewForms[card.trade_group_id].screenshots || []).length" class="image-grid compact-image-grid">
              <div v-for="(url, idx) in tradeReviewForms[card.trade_group_id].screenshots" :key="`${url}-${idx}`" class="image-tile">
                <img :src="url" alt="trade screenshot" class="image-preview" />
                <button type="button" class="secondary small-btn" @click="removeTradeScreenshot(card.trade_group_id, idx)">Remove</button>
              </div>
            </div>

            <div class="filter-action-row">
              <button @click="saveCardReview(card.trade_group_id)" :disabled="savingTrade === card.trade_group_id">{{ savingTrade === card.trade_group_id ? 'Saving...' : 'Save Trade Review' }}</button>
              <router-link class="inline-link" :to="`/trades/${card.trade_group_id}`">Open Detail</router-link>
            </div>
            <div v-if="tradeSaveErrors[card.trade_group_id]" class="save-error">
              {{ tradeSaveErrors[card.trade_group_id] }}
            </div>
            <div v-if="tradeSaveWarnings[card.trade_group_id]" class="save-warning">
              {{ tradeSaveWarnings[card.trade_group_id] }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="card workspace-secondary-card" ref="dailySectionRef">
      <div class="section-title">Daily Session Review</div>
      <div class="journal-form-grid workspace-field-grid" style="margin-bottom: 12px;">
        <label :title="fieldHint('market_regime')"><span>Market Regime</span><input v-model="form.market_regime" /></label>
        <label :title="fieldHint('daily_bias')"><span>Daily Bias</span><input v-model="form.daily_bias" /></label>
        <label><span>Did market behave as expected?</span><select v-model="marketExpectedSelection"><option value="">-</option><option value="true">Yes</option><option value="false">No</option></select></label>
      </div>

      <div class="journal-form-grid workspace-field-grid" style="margin-bottom: 12px;">
        <label :title="fieldHint('discipline')"><span>Discipline (1-10)</span><input type="number" min="1" max="10" v-model.number="form.discipline_score" /></label>
        <label><span>Overtrading?</span><select v-model="form.overtrading"><option :value="null">-</option><option :value="true">Yes</option><option :value="false">No</option></select></label>
        <label :title="fieldHint('followed_plan')"><span>Followed plan?</span><select v-model="form.followed_plan"><option :value="null">-</option><option :value="true">Yes</option><option :value="false">No</option></select></label>
      </div>

      <div :title="fieldHint('daily_mistake_tags')"><span>Daily Mistake Tags</span><div class="chip-wrap">
        <button v-for="tag in mistakeTags" :key="tag.id" type="button" :class="['trade-option-chip', { active: (form.mistake_tags || []).includes(tag.id) }]" @click="toggleDailyMistakeTag(tag.id)">{{ tag.name }}</button>
      </div></div>
      <div class="muted-copy" style="margin: 6px 0 10px;">Tag 管理（新增/编辑/删除）请前往 <router-link class="inline-link" to="/settings">Settings → Mistake Tags</router-link>。</div>
      <label :title="fieldHint('daily_screenshots')">
        <span>Daily Session Screenshots</span>
        <div class="helper-row">
          <input type="file" accept="image/*" multiple @change="uploadDailyScreenshots" />
          <span class="muted-copy" v-if="uploadingDailyImage">Uploading...</span>
        </div>
      </label>
      <div v-if="form.image_urls?.length" class="image-grid compact-image-grid">
        <div v-for="(url, idx) in form.image_urls" :key="`${url}-${idx}`" class="image-tile">
          <img :src="url" alt="daily screenshot" class="image-preview" />
          <button type="button" class="secondary small-btn" @click="removeDailyScreenshot(idx)">Remove</button>
        </div>
      </div>
      <div class="journal-text-grid">
        <label :title="fieldHint('market_summary')"><span>Market Summary</span><textarea v-model="form.market_summary" rows="3"></textarea></label>
        <label :title="fieldHint('biggest_mistake')"><span>Biggest Mistake</span><textarea v-model="form.biggest_mistake" rows="3"></textarea></label>
        <label :title="fieldHint('main_lesson')"><span>Main Lesson</span><textarea v-model="form.lessons" rows="3"></textarea></label>
        <label :title="fieldHint('tomorrow_plan')"><span>Tomorrow Plan</span><textarea v-model="form.next_day_plan" rows="3"></textarea></label>
      </div>
      <div class="filter-action-row">
        <button @click="saveDailyReview('draft')" :disabled="savingDaily">{{ savingDaily ? 'Saving...' : 'Save Draft' }}</button>
        <button class="secondary" @click="saveDailyReview('completed')" :disabled="savingDaily">Mark Complete</button>
      </div>
    </section>

    <section class="card workspace-tertiary-card" ref="positionSectionRef">
      <div class="section-title">Open Position Checkpoints</div>
      <div v-if="!queue.open_positions?.length" class="empty-row">No open positions.</div>
      <div v-for="item in queue.open_positions" :key="item.trade_group_id" class="journal-entry-card" style="margin-bottom:10px;">
        <div class="journal-entry-head"><div><strong>{{ item.symbol }}</strong> · Qty {{ item.open_qty }} · Avg cost {{ item.avg_open_cost || '-' }} · Opened {{ formatOpenedAt(item.opened_at) }}</div><button class="secondary small-btn" @click="togglePosition(item.trade_group_id)">{{ expandedPositions.includes(item.trade_group_id) ? 'Close' : 'Checkpoint' }}</button></div>
        <div v-if="expandedPositions.includes(item.trade_group_id)" class="accordion-body">
          <div class="journal-form-grid">
            <label :title="fieldHint('thesis_status')"><span>Thesis status</span><select v-model="positionForms[item.trade_group_id].status"><option value="open">still valid</option><option value="reduced">weakened</option><option value="closed">invalid</option></select></label>
            <label :title="fieldHint('checkpoint_time')"><span>Checkpoint Time</span><input type="datetime-local" v-model="positionForms[item.trade_group_id].checkpoint_time" /></label>
            <label :title="fieldHint('emotion_level')"><span>Emotion (1-10)</span><input type="number" min="1" max="10" v-model.number="positionForms[item.trade_group_id].emotion_level" /></label>
            <label :title="fieldHint('action_bias')"><span>Action bias</span><select v-model="positionForms[item.trade_group_id].action_bias"><option value="hold">hold</option><option value="reduce">reduce</option><option value="take_profit">take_profit</option><option value="stop_out">stop_out</option></select></label>
          </div>
          <label :title="fieldHint('hold_overnight')"><span>Why hold overnight</span><textarea v-model="positionForms[item.trade_group_id].carry_reason" rows="2"></textarea></label>
          <label :title="fieldHint('risk_tomorrow')"><span>Risk tomorrow</span><textarea v-model="positionForms[item.trade_group_id].gap_risk_note" rows="2"></textarea></label>
          <label :title="fieldHint('next_action')"><span>Next action</span><textarea v-model="positionForms[item.trade_group_id].next_session_plan" rows="2"></textarea></label>
          <div class="filter-action-row"><button @click="saveCheckpoint(item.trade_group_id)" :disabled="savingPosition === item.trade_group_id">{{ savingPosition === item.trade_group_id ? 'Saving...' : 'Save Checkpoint' }}</button></div>
        </div>
      </div>
    </section>
    </div>
    </template>

    <section v-else-if="journalTab === 'pretrade'" class="card">
      <div class="section-title">Pre-Trade Plan / Setup Snapshot</div>
      <div class="pretrade-module-card">
        <div class="section-title minor">① Market Context</div>
        <div class="journal-form-grid workspace-field-grid">
          <label :title="fieldHint('queue_date')"><span>Plan Date</span><input v-model="pretradeDate" type="date" @change="loadPretrade" @click="openDatePicker" @focus="openDatePicker" /></label>
          <label :title="fieldHint('session_focus')">
            <span>Session (multi-select)</span>
            <div class="multi-select-wrap">
              <button type="button" class="multi-select-trigger" @click="sessionDropdownOpen = !sessionDropdownOpen">
                {{ selectedSessionLabel }}
              </button>
              <div v-if="sessionDropdownOpen" class="multi-select-panel">
                <label v-for="opt in sessionOptions" :key="opt" class="multi-select-option">
                  <input type="checkbox" :checked="pretradeSessions.includes(opt)" @change="toggleSessionOption(opt)" />
                  <span>{{ opt }}</span>
                </label>
              </div>
            </div>
          </label>
          <label :title="fieldHint('market_regime')"><span>Market Regime <span class="required-asterisk">*</span></span><input v-model="pretradeForm.market_regime" :class="{ 'field-missing': pretradeSubmitAttempted && !pretradeForm.market_regime }" :placeholder="pretradeSubmitAttempted && !pretradeForm.market_regime ? 'Required field' : ''" /></label>
          <label :title="fieldHint('watchlist')"><span>Watchlist (comma-separated)</span><input v-model="watchlistText" placeholder="AAPL, NVDA, TSLA" /></label>
          <label :title="fieldHint('risk_budget_r')"><span>Risk Budget (R) <span class="required-asterisk">*</span></span><input type="number" step="0.1" v-model.number="pretradeForm.risk_budget_r" :class="{ 'field-missing': pretradeSubmitAttempted && !(Number(pretradeForm.risk_budget_r) > 0) }" :placeholder="pretradeSubmitAttempted && !(Number(pretradeForm.risk_budget_r) > 0) ? 'Required field' : ''" /></label>
        </div>
      </div>
      <div class="pretrade-module-card">
        <div class="section-title minor">② Strategy & Checklist</div>
        <div class="pretrade-textarea-grid">
          <label :title="fieldHint('game_plan')"><span>Game Plan</span><textarea v-model="pretradeForm.game_plan" rows="3"></textarea></label>
          <label :title="fieldHint('catalysts')"><span>Catalysts</span><textarea v-model="pretradeForm.catalysts" rows="3"></textarea></label>
        </div>
        <div>
          <span>Checklist</span>
          <div class="checklist-banner" :class="pretradeChecklistPassed ? 'status-good-block' : 'status-bad-block'">
            Score: {{ checklistPassCount }}/{{ checklistTotal }} · {{ pretradeChecklistPassed ? '✅ PASSED' : '❌ NOT PASSED' }}
          </div>
          <div class="pretrade-checklist-grid">
            <label :class="['checklist-item', pretradeChecklist.market_trending ? 'check-on' : 'check-off']"><span>{{ pretradeChecklist.market_trending ? '✓' : '✗' }}</span><input type="checkbox" v-model="pretradeChecklist.market_trending" /> Market trending</label>
            <label :class="['checklist-item', pretradeChecklist.volume_above_average ? 'check-on' : 'check-off']"><span>{{ pretradeChecklist.volume_above_average ? '✓' : '✗' }}</span><input type="checkbox" v-model="pretradeChecklist.volume_above_average" /> Volume above average</label>
            <label :class="['checklist-item', pretradeChecklist.no_major_news_risk ? 'check-on' : 'check-off']"><span>{{ pretradeChecklist.no_major_news_risk ? '✓' : '✗' }}</span><input type="checkbox" v-model="pretradeChecklist.no_major_news_risk" /> No major news risk</label>
            <label :class="['checklist-item', pretradeChecklist.clean_structure ? 'check-on' : 'check-off']"><span>{{ pretradeChecklist.clean_structure ? '✓' : '✗' }}</span><input type="checkbox" v-model="pretradeChecklist.clean_structure" /> Clean structure</label>
          </div>
        </div>
        <div class="risk-dashboard" :class="riskStatusClass">
          <div><strong>Risk Dashboard</strong></div>
          <div>🟢 Used: {{ usedRiskR.toFixed(2) }}R</div>
          <div>🟡 Remaining: {{ remainingRiskR.toFixed(2) }}R</div>
          <div>🔴 Max: {{ Number(pretradeForm.risk_budget_r || 0).toFixed(2) }}R</div>
          <div class="risk-progress">
            <div class="risk-progress-fill" :style="{ width: `${usedRiskPct}%` }">
              <span class="risk-progress-label">{{ usedRiskPct.toFixed(0) }}%</span>
            </div>
          </div>
        </div>
        <div v-if="riskLimitReached" class="save-error">Risk budget reached. New setup snapshots are blocked until budget is increased.</div>
        <div class="save-error" v-if="pretradeError">{{ pretradeError }}</div>
        <div class="filter-action-row">
          <button @click="savePretrade" :disabled="savingPretrade">{{ savingPretrade ? 'Saving...' : 'Save Pre-Trade Plan' }}</button>
        </div>
      </div>

      <div class="section-title" style="margin-top:14px;">③ Setup Snapshots</div>
      <div v-for="(row, idx) in snapshotForms" :key="`snap-${idx}`" class="journal-entry-card" style="margin-bottom:10px;">
        <div class="snapshot-row-head">
          <div class="section-title minor" style="margin:0;">Snapshot {{ idx + 1 }} · {{ row.symbol || 'No symbol' }}</div>
          <button type="button" class="secondary small-btn" @click="toggleSnapshotCard(row.local_id)">
            {{ expandedSnapshotCards.includes(row.local_id) ? 'Collapse' : 'Expand' }}
          </button>
        </div>
        <div v-if="expandedSnapshotCards.includes(row.local_id)">
        <div class="section-title minor">Basic</div>
        <div class="journal-form-grid workspace-field-grid">
          <label :title="fieldHint('snapshot_symbol')">
            <span>Symbol <span class="required-asterisk">*</span></span>
            <select v-model="row.symbol" :class="{ 'field-missing': isSnapshotMissing(row, 'symbol') }">
              <option value="">Select from watchlist</option>
              <option v-for="sym in watchlistOptions" :key="`wl-${sym}`" :value="sym">{{ sym }}</option>
            </select>
          </label>
          <label :title="fieldHint('snapshot_strategy')">
            <span>Strategy (optional)</span>
            <input v-model="row.strategy" :list="`snapshot-strategy-options-${row.local_id}`" placeholder="Opening Drive / 自定义..." />
          </label>
          <label :title="fieldHint('snapshot_direction')"><span>Direction <span class="required-asterisk">*</span></span><select v-model="row.direction" :class="{ 'field-missing': isSnapshotMissing(row, 'direction') }"><option value="long">long</option><option value="short">short</option></select></label>
        </div>
        <datalist :id="`snapshot-strategy-options-${row.local_id}`">
          <option value="Opening Drive"></option>
          <option value="VWAP Reversion"></option>
          <option value="Liquidity Sweep"></option>
        </datalist>
        <div class="section-title minor">Setup</div>
        <div class="journal-form-grid workspace-field-grid">
          <label :title="fieldHint('snapshot_setup_type')">
            <span>Setup <span class="required-asterisk">*</span></span>
            <input
              v-model="row.setup_merged"
              :list="`snapshot-setup-options-${row.local_id}`"
              :class="{ 'field-missing': isSnapshotMissing(row, 'setup_merged') }"
              :placeholder="isSnapshotMissing(row, 'setup_merged') ? 'Required field' : 'breakout / setup tag / custom...'"
            />
          </label>
          <datalist :id="`snapshot-setup-options-${row.local_id}`">
            <option value="breakout"></option>
            <option value="pullback"></option>
            <option value="reversal"></option>
            <option value="range"></option>
            <option v-for="item in setupTags" :key="`setup-opt-${item.id}`" :value="item.name"></option>
          </datalist>
          <label :title="fieldHint('snapshot_timeframe')"><span>Timeframe <span class="required-asterisk">*</span></span><select v-model="row.timeframe" :class="{ 'field-missing': isSnapshotMissing(row, 'timeframe') }"><option value="1m">1m</option><option value="5m">5m</option><option value="15m">15m</option><option value="1h">1h</option><option value="1d">1d</option></select></label>
          <label :title="fieldHint('snapshot_confidence')"><span>Confidence (1-10)</span><input type="number" min="1" max="10" v-model.number="row.confidence_score" /></label>
          <label :title="fieldHint('snapshot_checklist_passed')"><span>Checklist passed <span class="required-asterisk">*</span></span><select v-model="row.checklist_passed"><option :value="true">Yes</option><option :value="false">No</option></select></label>
        </div>
        <div class="section-title minor">Execution Plan</div>
        <div class="journal-form-grid workspace-field-grid">
          <label>
            <span>Trading Mode</span>
            <div class="trading-mode-switch">
              <label class="mode-option"><input type="radio" value="planned" v-model="row.trading_mode" /> Planned Trade</label>
              <label class="mode-option"><input type="radio" value="reactive" v-model="row.trading_mode" /> Reactive Trade</label>
            </div>
          </label>
        </div>
        <div class="journal-form-grid workspace-field-grid">
          <label v-if="row.trading_mode !== 'reactive'" :title="fieldHint('snapshot_planned_entry')"><span>Planned Entry <span class="required-asterisk">*</span></span><input type="number" step="0.0001" v-model.number="row.planned_entry" :class="{ 'field-missing': isSnapshotMissing(row, 'planned_entry') }" :placeholder="isSnapshotMissing(row, 'planned_entry') ? 'Required field' : ''" /></label>
          <label v-else><span>Entry</span><input value="auto (from execution)" disabled /></label>
          <label :title="fieldHint('snapshot_planned_stop')"><span>{{ row.trading_mode === 'reactive' ? 'Stop (optional)' : 'Planned Stop' }} <span v-if="row.trading_mode !== 'reactive'" class="required-asterisk">*</span></span><input type="number" step="0.0001" v-model.number="row.planned_stop" :class="{ 'field-missing': row.trading_mode !== 'reactive' && isSnapshotMissing(row, 'planned_stop') }" :placeholder="row.trading_mode === 'reactive' ? 'Optional' : (isSnapshotMissing(row, 'planned_stop') ? 'Required field' : '')" /></label>
          <label :title="fieldHint('snapshot_planned_target')"><span>{{ row.trading_mode === 'reactive' ? 'Target (optional)' : 'Planned Target' }} <span v-if="row.trading_mode !== 'reactive'" class="required-asterisk">*</span></span><input type="number" step="0.0001" v-model.number="row.planned_target" :class="{ 'field-missing': row.trading_mode !== 'reactive' && isSnapshotMissing(row, 'planned_target') }" :placeholder="row.trading_mode === 'reactive' ? 'Optional' : (isSnapshotMissing(row, 'planned_target') ? 'Required field' : '')" /></label>
          <label :title="fieldHint('snapshot_planned_risk')"><span>Planned Risk (R) <span class="required-asterisk">*</span></span><input type="number" step="0.1" min="0.1" v-model.number="row.planned_risk_r" :class="{ 'field-missing': isSnapshotMissing(row, 'planned_risk_r') }" :placeholder="isSnapshotMissing(row, 'planned_risk_r') ? 'Required field' : ''" /></label>
        </div>
        <div v-if="row.trading_mode === 'reactive'" class="journal-form-grid workspace-field-grid">
          <label><span>Entry Reason</span><textarea v-model="row.entry_reason" rows="2" placeholder="Volume spike at resistance"></textarea></label>
          <label><span>Stop Logic</span><textarea v-model="row.stop_logic" rows="2" placeholder="below liquidity sweep"></textarea></label>
        </div>
        <div class="muted-copy" :class="confidenceClass(row.confidence_score)">Confidence signal: {{ confidenceSignal(row.confidence_score) }}</div>
        <div v-if="row.trading_mode !== 'reactive'">
          <div class="section-title minor">Logic</div>
          <div class="journal-form-grid workspace-field-grid">
            <label :title="fieldHint('snapshot_trigger_type')"><span>Trigger Type</span><select v-model="row.trigger_type"><option value="break_premarket_high">break_premarket_high</option><option value="volume_spike">volume_spike</option><option value="vwap_reclaim">vwap_reclaim</option><option value="custom">custom</option></select></label>
            <label :title="fieldHint('snapshot_invalidation_type')"><span>Invalidation Type</span><select v-model="row.invalidation_type"><option value="lose_vwap">lose_vwap</option><option value="fail_breakout_2m">fail_breakout_2m</option><option value="break_structure">break_structure</option><option value="custom">custom</option></select></label>
          </div>
          <label :title="fieldHint('snapshot_trigger_condition')"><span>Trigger condition</span><textarea v-model="row.trigger_condition" rows="2"></textarea></label>
          <label :title="fieldHint('snapshot_invalidation')"><span>Invalidation</span><textarea v-model="row.invalidation" rows="2"></textarea></label>
        </div>
        <div v-if="!row.checklist_passed" class="save-warning">Checklist not fully passed — allowed, but review confidence should be conservative.</div>
        <div class="save-error" v-if="snapshotErrors[row.local_id]">{{ snapshotErrors[row.local_id] }}</div>
        <div class="filter-action-row">
          <button @click="saveSnapshot(row)" :disabled="savingSnapshotId === row.local_id">{{ savingSnapshotId === row.local_id ? 'Saving...' : 'Save Snapshot' }}</button>
        </div>
        </div>
      </div>
      <div class="filter-action-row">
        <button class="secondary" @click="addSnapshotRow" :disabled="riskLimitReached">Add Snapshot</button>
        <button class="secondary" @click="removeLastSnapshotRow" :disabled="!snapshotForms.length">Delete Snapshot</button>
      </div>
    </section>

    <section v-else-if="journalTab === 'analytics'" class="card analytics-surface">
      <div class="section-title">Trade Review Analytics</div>
      <div class="filter-action-row" style="margin-top:0;">
        <button @click="loadAnalytics" :disabled="loadingAnalytics">{{ loadingAnalytics ? 'Loading...' : 'Refresh Analytics' }}</button>
      </div>
      <div v-if="analyticsError" class="save-error">{{ analyticsError }}</div>
      <div v-if="!analytics.by_strategy.length && !analytics.by_session.length && !analytics.by_symbol.length" class="empty-row">
        No analytics data yet. Save Trade Reviews with `realized_r` / `session` / `strategy` first.
      </div>
      <div v-else>
        <div class="analytics-kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">Trades</div>
            <div class="kpi-value">{{ analytics.summary?.trades ?? 0 }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">PnL</div>
            <div :class="['kpi-value', (analytics.summary?.total_pnl ?? 0) >= 0 ? 'kpi-positive' : 'kpi-negative']">{{ analytics.summary?.total_pnl ?? 0 }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Win Rate</div>
            <div class="kpi-value">{{ summaryWinRate }}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Profit Factor</div>
            <div class="kpi-value">{{ analytics.summary?.profit_factor ?? '-' }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Max DD</div>
            <div :class="['kpi-value', (analytics.summary?.max_drawdown ?? 0) >= 0 ? 'kpi-positive' : 'kpi-negative']">{{ analytics.summary?.max_drawdown ?? 0 }}</div>
          </div>
        </div>

        <div class="insight-highlight-card">
          <div class="section-title minor">💡 Actionable Insights</div>
          <div v-if="!(analytics.insights || []).length" class="muted-copy">Not enough data to generate insights.</div>
          <div v-for="(line, idx) in analytics.insights || []" :key="`ins-${idx}`" class="review-item">👉 {{ line }}</div>
        </div>

        <div class="journal-entry-card analytics-panel-card" style="margin-top:10px;">
          <div class="section-title minor">Strategy Edge Ranking</div>
          <div class="analytics-table-wrap">
            <table class="analytics-table">
              <thead>
                <tr>
                  <th>Strategy</th><th>N</th><th>Win</th><th>Avg R</th><th>Exp</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in analytics.strategy_edge_ranking || []" :key="`edge-${row.key}`">
                  <td>{{ row.key }}</td>
                  <td>{{ row.trades }}</td>
                  <td>{{ row.win_rate }}%</td>
                  <td>{{ row.avg_r ?? '-' }}</td>
                  <td>{{ row.expectancy ?? '-' }}</td>
                  <td>{{ row.action }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="journal-text-grid" style="margin-top:10px;">
          <div class="journal-entry-card">
            <div class="section-title minor">🔥 Biggest Loss Drivers</div>
            <div v-if="!(analytics.mistake_impact || []).length" class="muted-copy">No mistake-tag data yet.</div>
            <div v-for="(row, idx) in analytics.mistake_impact || []" :key="`mist-${row.key}`" class="review-item">
              {{ idx + 1 }}. {{ row.key }} → Avg R {{ row.avg_r ?? '-' }} · Win {{ row.win_rate }}% · PnL {{ row.total_pnl }}
            </div>
          </div>
          <div class="journal-entry-card">
            <div class="section-title minor">📊 Execution Quality</div>
            <div class="analytics-plan-grid">
              <div class="reflection-box reflection-good">
                <div class="reflection-title">✔ Followed Plan</div>
                <div>Win {{ analytics.plan_adherence?.followed?.win_rate ?? '-' }}% · Exp {{ analytics.plan_adherence?.followed?.expectancy ?? '-' }}</div>
              </div>
              <div class="reflection-box reflection-bad">
                <div class="reflection-title">❌ Did NOT Follow</div>
                <div>Win {{ analytics.plan_adherence?.not_followed?.win_rate ?? '-' }}% · Exp {{ analytics.plan_adherence?.not_followed?.expectancy ?? '-' }}</div>
              </div>
            </div>
            <div class="review-item">⚠ Late Entry {{ analytics.plan_adherence?.late_entry_rate ?? '-' }}% · ⚠ Broke Stop {{ analytics.plan_adherence?.broke_stop_rate ?? '-' }}% · Sample {{ analytics.plan_adherence?.compare_sample_size ?? 0 }}</div>
          </div>
        </div>

        <div class="journal-entry-card" style="margin-top:10px;">
          <div class="section-title minor">Compare</div>
          <div class="journal-form-grid workspace-field-grid">
            <label><span>Dimension</span>
              <select v-model="compareDimension">
                <option v-for="item in analyticsDimensionOptions" :key="item.key" :value="item.key">{{ item.label }}</option>
              </select>
            </label>
            <label><span>Left</span>
              <select v-model="compareLeftKey"><option v-for="key in comparisonOptions" :key="`l-${key}`" :value="key">{{ key }}</option></select>
            </label>
            <label><span>Right</span>
              <select v-model="compareRightKey"><option v-for="key in comparisonOptions" :key="`r-${key}`" :value="key">{{ key }}</option></select>
            </label>
          </div>
          <div class="muted-copy" v-if="leftCompareRow">{{ compareLeftKey }} → N {{ leftCompareRow.trades }} · Win {{ leftCompareRow.win_rate }}% · PnL {{ leftCompareRow.total_pnl }} · Exp {{ leftCompareRow.expectancy }} · PF {{ leftCompareRow.profit_factor ?? '-' }}</div>
          <div class="muted-copy" v-if="rightCompareRow">{{ compareRightKey }} → N {{ rightCompareRow.trades }} · Win {{ rightCompareRow.win_rate }}% · PnL {{ rightCompareRow.total_pnl }} · Exp {{ rightCompareRow.expectancy }} · PF {{ rightCompareRow.profit_factor ?? '-' }}</div>
        </div>

        <div class="journal-text-grid" style="margin-top:10px;">
          <div class="journal-entry-card analytics-panel-card">
            <div class="section-title minor">By Strategy</div>
            <div v-for="row in analytics.by_strategy" :key="`s-${row.key}`" class="analytics-stat-row">
              <strong>{{ row.key }}</strong>
              <span class="badge">N {{ row.trades }}</span>
              <span class="badge">Win {{ row.win_rate }}%</span>
              <span :class="['badge', row.total_pnl >= 0 ? 'badge-profit' : 'badge-loss']">PnL {{ row.total_pnl }}</span>
              <span class="badge">AvgR {{ row.avg_r ?? '-' }}</span>
              <span class="badge">Exp {{ row.expectancy ?? '-' }}</span>
            </div>
          </div>
          <div class="journal-entry-card analytics-panel-card">
            <div class="section-title minor">By Session</div>
            <div v-for="row in analytics.by_session" :key="`ss-${row.key}`" class="analytics-stat-row">
              <strong>{{ row.key }}</strong>
              <span class="badge">N {{ row.trades }}</span>
              <span class="badge">Win {{ row.win_rate }}%</span>
              <span :class="['badge', row.total_pnl >= 0 ? 'badge-profit' : 'badge-loss']">PnL {{ row.total_pnl }}</span>
              <span class="badge">Exp {{ row.expectancy ?? '-' }}</span>
            </div>
          </div>
          <div class="journal-entry-card analytics-panel-card">
            <div class="section-title minor">By Symbol</div>
            <div v-for="row in analytics.by_symbol" :key="`sym-${row.key}`" class="analytics-stat-row">
              <strong>{{ row.key }}</strong>
              <span class="badge">N {{ row.trades }}</span>
              <span class="badge">Win {{ row.win_rate }}%</span>
              <span :class="['badge', row.total_pnl >= 0 ? 'badge-profit' : 'badge-loss']">PnL {{ row.total_pnl }}</span>
              <span class="badge">Exp {{ row.expectancy ?? '-' }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="tv-dashboard-chart-grid tv-dashboard-chart-grid-triple" style="margin-top:12px;">
        <TradesVizChart title="Equity Curve" subtitle="Cumulative realized PnL with baseline" :categories="equityCategories" :series="equitySeries" default-type="line" :height="180" />
        <TradesVizChart title="R Distribution" subtitle="Per-trade R multiples + baseline" :categories="rDistributionCategories" :series="rDistributionSeries" default-type="bar" :height="180" />
        <TradesVizChart title="Holding Time vs PnL" subtitle="Includes simple trend line" :categories="holdingScatterCategories" :series="holdingScatterSeries" default-type="line" :height="180" />
      </div>
    </section>

    <div v-if="confirmDialog.visible" class="confirm-modal-mask" @click="cancelConfirm">
      <div class="confirm-modal-card" @click.stop>
        <div class="section-title minor">{{ confirmDialog.title }}</div>
        <div class="muted-copy" style="margin-top:6px;">{{ confirmDialog.message }}</div>
        <div class="filter-action-row" style="margin-top:12px;">
          <button class="secondary" @click="cancelConfirm">{{ confirmDialog.cancelText }}</button>
          <button @click="acceptConfirm">{{ confirmDialog.confirmText }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import TradesVizChart from '../components/TradesVizChart.vue'
import {
  createDailyReview,
  fetchMistakeTags,
  fetchPretradePlans,
  fetchReviewQueue,
  fetchSetupSnapshots,
  fetchSetupTags,
  fetchTradeReviewAnalyticsSummary,
  savePretradePlan,
  savePositionCheckpoint,
  updatePretradePlan,
  updateSetupSnapshot,
  saveSetupSnapshot,
  deleteSetupSnapshot,
  saveTradeReview,
  uploadDailyReviewImages,
} from '../api/journal'

const queueDate = ref(new Date().toISOString().slice(0, 10))
const journalTab = ref('pretrade')
const queue = ref({ summary: {}, closed_trades: [], open_positions: [] })
const expandedCards = ref([])
const expandedPositions = ref([])
const tradeReviewForms = ref({})
const positionForms = ref({})
const setupTags = ref([])
const mistakeTags = ref([])
const savingTrade = ref(null)
const savingDaily = ref(false)
const savingPosition = ref(null)
const uploadingTrade = ref(null)
const uploadingDailyImage = ref(false)
const tradeSaveErrors = ref({})
const tradeSaveWarnings = ref({})
const maxLossSelection = ref('')
const tradeSectionRef = ref(null)
const dailySectionRef = ref(null)
const positionSectionRef = ref(null)
const pretradeDate = ref(new Date().toISOString().slice(0, 10))
const pretradeForm = ref({ id: null, plan_date: pretradeDate.value, session: 'premarket', market_regime: '', watchlist: [], catalysts: '', game_plan: '', pre_trade_checklist: {}, risk_budget_r: null, notes: '' })
const pretradeSessions = ref(['premarket'])
const sessionOptions = ['premarket', 'open', 'midday', 'close']
const sessionDropdownOpen = ref(false)
const watchlistText = ref('')
const pretradeChecklist = ref({ market_trending: false, volume_above_average: false, no_major_news_risk: false, clean_structure: false })
const snapshotForms = ref([])
const expandedSnapshotCards = ref([])
const savingPretrade = ref(false)
const savingSnapshotId = ref(null)
const pretradeError = ref('')
const snapshotErrors = ref({})
const pretradeSubmitAttempted = ref(false)
const snapshotSubmitAttempted = ref({})
const queuePretradeReady = ref(true)
const queuePretradeMessage = ref('')
const queuePretradePlan = ref(null)
const marketExpectedSelection = ref('')
const analytics = ref({ by_strategy: [], by_session: [], by_symbol: [], strategy_edge_ranking: [], mistake_impact: [], plan_adherence: {}, insights: [] })
const loadingAnalytics = ref(false)
const analyticsError = ref('')
const compareDimension = ref('by_strategy')
const compareLeftKey = ref('')
const compareRightKey = ref('')
const confirmDialog = ref({ visible: false, title: 'Confirm', message: '', confirmText: 'Confirm', cancelText: 'Cancel' })
const actionNotice = ref('')
let confirmResolver = null
let actionNoticeTimer = null

function showActionNotice(message) {
  actionNotice.value = message
  if (actionNoticeTimer) clearTimeout(actionNoticeTimer)
  actionNoticeTimer = setTimeout(() => {
    actionNotice.value = ''
    actionNoticeTimer = null
  }, 2200)
}

const form = ref({ review_date: queueDate.value, review_status: 'draft', strategy: '', market_regime: '', daily_bias: '', market_summary: '', biggest_mistake: '', lessons: '', next_day_plan: '', related_trade_groups: [], session: '', market_condition: '', confidence_score: null, discipline_score: null, emotional_control_score: null, focus_score: null, max_daily_loss_respected: null, followed_plan: null, overtrading: null, market_behaved_as_expected: null, mistake_tags: [], image_urls: [] })

const completionStats = computed(() => {
  const closedTrades = queue.value.summary.closed_trade_count || 0
  const openPositions = queue.value.summary.open_position_count || 0
  const total = closedTrades + openPositions + 1
  const doneTrades = (queue.value.closed_trades || []).filter((t) => (t.review_completeness || 0) >= 80).length
  const donePositions = (queue.value.open_positions || []).filter((p) => p.latest_checkpoint_id).length
  const doneDaily = queue.value.summary.daily_review_completed ? 1 : 0
  return { total, doneTrades, donePositions, doneDaily, completed: doneTrades + donePositions + doneDaily }
})

const completionRate = computed(() => {
  const { total, completed } = completionStats.value
  return total ? Math.round((completed / total) * 100) : 0
})

const completionSummary = computed(() => {
  const { completed, total, doneTrades, donePositions, doneDaily } = completionStats.value
  return `${completed}/${total} · T ${doneTrades} · P ${donePositions} · D ${doneDaily}`
})

const FIELD_HINTS = {
  queue_date: '选择要处理复盘队列的交易日期。',
  trade_strategy: '本笔交易使用的策略名称/方向。',
  setup: '交易形态/模式（如 Breakout、Pullback）。',
  grade: '本笔交易综合评级（A最好）。',
  would_take_again: '如果再来一次，你是否还会做这笔交易。',
  entry_q: '1-5分：入场质量，5=非常理想。',
  exit_q: '1-5分：出场执行质量，5=非常理想。',
  risk_q: '1-5分：风险控制质量（仓位/止损执行）。',
  followed_plan: '是否按原计划执行。',
  plan_follow_take_again: '将 Followed plan 与 Would take again 合并后的快速判断。',
  realized_r: '本笔交易R倍数结果（如 +1R / -0.5R）。',
  thesis: '这笔交易的核心逻辑与依据。',
  what_to_improve: '这笔交易后续可改进点。',
  next_time_rule: '强制改进规则：If [X happens] → I will [Y]。',
  mistake_tags: '本笔交易出现的问题标签（可多选）。',
  screenshots: '上传该笔交易相关截图，用于复盘留档。',
  market_regime: '当天主要市场环境（趋势/震荡等）。',
  daily_bias: '当日主观偏向（看多/看空/中性）。',
  session_focus: '复盘重点所在时段（开盘/中段/尾盘等）。',
  market_condition: '当天更细的行情状态标签。',
  strategy_focus: '当天重点执行的策略主题。',
  conviction: '1-10分：当日交易信念强度。',
  discipline: '1-10分：纪律执行程度。',
  emotional_control: '1-10分：情绪控制程度。',
  max_daily_loss: '是否遵守了日亏损上限。',
  market_summary: '对市场表现的简要总结。',
  biggest_mistake: '当天最关键的错误。',
  main_lesson: '当天最重要的经验教训。',
  tomorrow_plan: '次日执行计划。',
  daily_mistake_tags: '当天层面的错误标签（可多选）。',
  daily_screenshots: '上传当日复盘截图。',
  thesis_status: '隔夜持仓原始逻辑当前是否仍成立。',
  hold_overnight: '继续持仓到次日的原因。',
  risk_tomorrow: '次日可能面临的主要风险。',
  next_action: '次日计划动作（持有/减仓/平仓条件）。',
  primary_mistake_type: '错误主类型硬分类，用于后续成本归因。',
  mistake_severity: '错误严重度硬分类。',
  rule_violation_type: '违规规则类型硬分类。',
  watchlist: '盘前重点观察标的列表。',
  game_plan: '盘前执行剧本与优先级。',
  catalysts: '盘前重要事件/催化剂。',
  linked_snapshot: '可选：关联到本笔交易对应的盘前 Snapshot，用于计划与执行对比。',
  focus_score: '1-5分：专注度评分，5=非常专注。',
  checkpoint_time: '本次持仓检查的时间点。',
  emotion_level: '1-10分：当前情绪强度，越高表示情绪波动越明显。',
  action_bias: '本次检查后偏向动作（继续持有/减仓/止盈/止损）。',
  risk_budget_r: '当天计划可使用的最大风险预算（R）。',
  snapshot_symbol: '该 Snapshot 对应的交易标的代码。',
  snapshot_strategy: '该 Setup 的策略名称或方向。',
  snapshot_direction: '计划方向：做多(long)或做空(short)。',
  snapshot_setup_type: '统一 Setup 字段（可选预设、标签或自定义）。',
  snapshot_timeframe: '该 Setup 主要参考的时间周期。',
  snapshot_confidence: '1-10分：该 Setup 的主观把握度。',
  snapshot_setup_tag: '从 Setup 标签库中选择对应类型（可选）。',
  snapshot_checklist_passed: '该 Setup 是否通过你的盘前检查清单。',
  snapshot_planned_entry: '计划入场价格。',
  snapshot_planned_stop: '计划止损价格。',
  snapshot_planned_target: '计划止盈价格。',
  snapshot_planned_risk: '本 Setup 计划承担的风险（R）。',
  snapshot_trigger_type: '触发该 Setup 的条件类型。',
  snapshot_invalidation_type: '使该 Setup 失效的条件类型。',
  snapshot_trigger_condition: '触发条件的详细描述。',
  snapshot_invalidation: '失效条件的详细描述。',
}

function fieldHint(key) {
  return FIELD_HINTS[key] || ''
}

function syncLabelTitleTargets() {
  nextTick(() => {
    const labels = document.querySelectorAll('.review-workspace-page label[title]')
    labels.forEach((label) => {
      const hint = label.getAttribute('title')
      const span = label.querySelector('span')
      if (hint && span) span.setAttribute('title', hint)
    })
  })
}

function formatOpenedAt(value) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return String(value)
  return dt.toLocaleString()
}

function isSnapshotMissing(row, key) {
  if (!snapshotSubmitAttempted.value[row.local_id]) return false
  if (key === 'planned_risk_r') return !(Number(row.planned_risk_r) > 0)
  if (key === 'setup_merged') return !String(row.setup_merged || '').trim()
  if (['planned_entry', 'planned_stop', 'planned_target'].includes(key)) return row[key] == null || row[key] === ''
  return !row[key]
}

function toggleSessionOption(option) {
  const set = new Set(pretradeSessions.value || [])
  if (set.has(option)) set.delete(option)
  else set.add(option)
  pretradeSessions.value = Array.from(set)
}

function handleDocumentClick(event) {
  if (!sessionDropdownOpen.value) return
  const target = event?.target
  if (target && typeof target.closest === 'function' && target.closest('.multi-select-wrap')) return
  sessionDropdownOpen.value = false
}

function askConfirm({ title = 'Confirm', message = 'Are you sure?', confirmText = 'Confirm', cancelText = 'Cancel' } = {}) {
  confirmDialog.value = { visible: true, title, message, confirmText, cancelText }
  return new Promise((resolve) => {
    confirmResolver = resolve
  })
}

function acceptConfirm() {
  if (confirmResolver) confirmResolver(true)
  confirmResolver = null
  confirmDialog.value.visible = false
}

function cancelConfirm() {
  if (confirmResolver) confirmResolver(false)
  confirmResolver = null
  confirmDialog.value.visible = false
}

const analyticsDimensionOptions = computed(() => ([
  { key: 'by_strategy', label: 'Strategy' },
  { key: 'by_session', label: 'Session' },
  { key: 'by_symbol', label: 'Symbol' },
]))

const analyticsRowsForDimension = computed(() => analytics.value?.[compareDimension.value] || [])
const comparisonOptions = computed(() => analyticsRowsForDimension.value.map((row) => row.key))
const leftCompareRow = computed(() => analyticsRowsForDimension.value.find((row) => row.key === compareLeftKey.value) || null)
const rightCompareRow = computed(() => analyticsRowsForDimension.value.find((row) => row.key === compareRightKey.value) || null)
const summaryWinRate = computed(() => {
  const wins = Number(analytics.value?.summary?.wins || 0)
  const trades = Number(analytics.value?.summary?.trades || 0)
  if (!trades) return 0
  return ((wins / trades) * 100).toFixed(1)
})
const equityCategories = computed(() => (analytics.value.equity_curve || []).map((p) => p.date))
const equitySeries = computed(() => {
  const curve = (analytics.value.equity_curve || []).map((p) => p.equity)
  return [
    { name: 'Equity', data: curve },
    { name: 'Baseline 0', data: curve.map(() => 0) },
  ]
})
const rDistributionCategories = computed(() => (analytics.value.r_distribution || []).map((_, idx) => `T${idx + 1}`))
const rDistributionSeries = computed(() => {
  const dist = analytics.value.r_distribution || []
  return [
    { name: 'R Multiple', data: dist },
    { name: 'Baseline 0', data: dist.map(() => 0) },
  ]
})
const holdingScatterCategories = computed(() => (analytics.value.holding_vs_pnl || []).map((_, idx) => `P${idx + 1}`))
const holdingScatterSeries = computed(() => [
  { name: 'Holding Minutes', data: (analytics.value.holding_vs_pnl || []).map((p) => p.holding_minutes) },
  { name: 'PnL', data: (analytics.value.holding_vs_pnl || []).map((p) => p.pnl) },
  { name: 'PnL Trend', data: holdingTrend.value },
])
const holdingTrend = computed(() => {
  const rows = analytics.value.holding_vs_pnl || []
  if (rows.length < 2) return rows.map((p) => p.pnl)
  const n = rows.length
  const xs = rows.map((_, idx) => idx + 1)
  const ys = rows.map((p) => Number(p.pnl || 0))
  const sumX = xs.reduce((a, b) => a + b, 0)
  const sumY = ys.reduce((a, b) => a + b, 0)
  const sumXY = xs.reduce((a, x, idx) => a + (x * ys[idx]), 0)
  const sumXX = xs.reduce((a, x) => a + (x * x), 0)
  const slope = ((n * sumXY) - (sumX * sumY)) / Math.max(1, ((n * sumXX) - (sumX * sumX)))
  const intercept = (sumY - (slope * sumX)) / n
  return xs.map((x) => Number((intercept + (slope * x)).toFixed(2)))
})
const selectedSessionLabel = computed(() => {
  if (!pretradeSessions.value.length) return 'Select sessions'
  return pretradeSessions.value.join(', ')
})
const watchlistOptions = computed(() => {
  const items = watchlistText.value.split(',').map((v) => v.trim().toUpperCase()).filter(Boolean)
  return Array.from(new Set(items))
})

function parseSnapshotNotes(snapshotNotes = '') {
  const text = String(snapshotNotes || '')
  const modeMatch = text.match(/\[MODE\]\s*(planned|reactive)/i)
  const entryReasonMatch = text.match(/\[ENTRY_REASON\]\s*(.+)/i)
  const stopLogicMatch = text.match(/\[STOP_LOGIC\]\s*(.+)/i)
  return {
    trading_mode: modeMatch ? modeMatch[1].toLowerCase() : 'planned',
    entry_reason: entryReasonMatch ? entryReasonMatch[1].trim() : '',
    stop_logic: stopLogicMatch ? stopLogicMatch[1].trim() : '',
  }
}

function toSnapshotNotes(row) {
  const mode = row.trading_mode === 'reactive' ? 'reactive' : 'planned'
  const lines = [`[MODE] ${mode}`]
  if (mode === 'reactive') {
    if (row.entry_reason) lines.push(`[ENTRY_REASON] ${row.entry_reason}`)
    if (row.stop_logic) lines.push(`[STOP_LOGIC] ${row.stop_logic}`)
  }
  return lines.join('\n')
}

function toggleCard(id) { expandedCards.value = expandedCards.value.includes(id) ? expandedCards.value.filter((v) => v !== id) : [...expandedCards.value, id] }
function togglePosition(id) { expandedPositions.value = expandedPositions.value.includes(id) ? expandedPositions.value.filter((v) => v !== id) : [...expandedPositions.value, id] }
function toggleSnapshotCard(localId) {
  expandedSnapshotCards.value = expandedSnapshotCards.value.includes(localId)
    ? expandedSnapshotCards.value.filter((v) => v !== localId)
    : [...expandedSnapshotCards.value, localId]
}
function openDatePicker(event) {
  const dateInput = event?.target
  if (dateInput && typeof dateInput.showPicker === 'function') dateInput.showPicker()
}

function confidenceSignal(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'Not set'
  if (n < 5) return 'Low confidence (<5): not recommended'
  if (n >= 8) return 'High confidence'
  return 'Normal confidence'
}

function confidenceClass(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  if (n < 5) return 'status-bad'
  if (n >= 8) return 'status-good'
  return ''
}

function toggleDailyMistakeTag(tagId) {
  const set = new Set(form.value.mistake_tags || [])
  if (set.has(tagId)) set.delete(tagId)
  else set.add(tagId)
  form.value.mistake_tags = Array.from(set)
}

function toggleTradeMistakeTag(tradeGroupId, tagId) {
  const set = new Set(tradeReviewForms.value[tradeGroupId].mistake_tags || [])
  if (set.has(tagId)) set.delete(tagId)
  else set.add(tagId)
  tradeReviewForms.value[tradeGroupId].mistake_tags = Array.from(set)
}

function hydrateCardForms(cards) {
  const next = {}
  cards.forEach((card) => {
    const review = card.trade_review || {}
    next[card.trade_group_id] = {
      trade_group: card.trade_group_id,
      selected_snapshot: card.selected_snapshot_id ? Number(card.selected_snapshot_id) : null,
      strategy: review.strategy || '',
      setup: review.setup || null,
      final_grade: review.final_grade || '',
      would_take_again: review.would_take_again || '',
      thesis: review.thesis || '',
      entry_quality: review.entry_quality,
      exit_quality: review.exit_quality,
      risk_management: review.risk_management,
      followed_plan: review.followed_plan ?? null,
      plan_follow_take_again: review.would_take_again || (review.followed_plan == null ? '' : (review.followed_plan ? 'yes' : 'no')),
      primary_mistake_type: review.primary_mistake_type || 'none',
      mistake_severity: review.mistake_severity || 'low',
      rule_violation_type: review.rule_violation_type || 'none',
      what_to_improve: review.what_to_improve || '',
      mistake_tags: review.mistake_tags || [],
      screenshots: review.screenshots || [],
      realized_r: review.realized_r,
    }
  })
  tradeReviewForms.value = next
}

function hydratePositionForms(positions) {
  const next = {}
  positions.forEach((item) => {
    next[item.trade_group_id] = {
      trade_group: item.trade_group_id,
      review_date: queueDate.value,
      status: 'open',
      checkpoint_time: `${queueDate.value}T09:30`,
      carry_reason: '',
      gap_risk_note: '',
      emotion_level: null,
      action_bias: 'hold',
      next_session_plan: '',
    }
  })
  positionForms.value = next
}

function hydrateDailyReview(dailyReview) {
  if (!dailyReview) {
    form.value = { review_date: queueDate.value, review_status: 'draft', strategy: '', market_regime: '', daily_bias: '', market_summary: '', biggest_mistake: '', lessons: '', next_day_plan: '', related_trade_groups: queue.value.closed_trades.map((item) => item.trade_group_id), session: '', market_condition: '', confidence_score: null, discipline_score: null, emotional_control_score: null, focus_score: null, max_daily_loss_respected: null, followed_plan: null, overtrading: null, market_behaved_as_expected: null, mistake_tags: [], image_urls: [] }
    maxLossSelection.value = ''
    marketExpectedSelection.value = ''
    return
  }
  form.value = {
    review_date: queueDate.value,
    review_status: dailyReview.review_status || 'draft',
    strategy: dailyReview.strategy || '',
    market_regime: dailyReview.market_regime || '',
    daily_bias: dailyReview.daily_bias || '',
    market_summary: dailyReview.market_summary || '',
    biggest_mistake: dailyReview.biggest_mistake || '',
    lessons: dailyReview.lessons || '',
    next_day_plan: dailyReview.next_day_plan || '',
    related_trade_groups: (dailyReview.related_trade_groups || []).length ? dailyReview.related_trade_groups : queue.value.closed_trades.map((item) => item.trade_group_id),
    session: dailyReview.session || '',
    market_condition: dailyReview.market_condition || '',
    confidence_score: dailyReview.confidence_score,
    discipline_score: dailyReview.discipline_score,
    emotional_control_score: dailyReview.emotional_control_score,
    focus_score: dailyReview.focus_score,
    max_daily_loss_respected: dailyReview.max_daily_loss_respected,
    followed_plan: dailyReview.followed_plan ?? null,
    overtrading: dailyReview.overtrading ?? null,
    market_behaved_as_expected: dailyReview.market_behaved_as_expected ?? null,
    mistake_tags: dailyReview.mistake_tags || [],
    image_urls: (dailyReview.images || []).map((item) => item.image_url),
  }
  maxLossSelection.value = dailyReview.max_daily_loss_respected == null ? '' : String(dailyReview.max_daily_loss_respected)
  marketExpectedSelection.value = dailyReview.market_behaved_as_expected == null ? '' : String(dailyReview.market_behaved_as_expected)
}

async function loadMetaTags() {
  const [setupRes, mistakeRes] = await Promise.all([fetchSetupTags(), fetchMistakeTags()])
  setupTags.value = setupRes.data?.results || setupRes.data || []
  mistakeTags.value = mistakeRes.data?.results || mistakeRes.data || []
}

async function loadQueue() {
  const res = await fetchReviewQueue(queueDate.value)
  queue.value = res.data || { summary: {}, closed_trades: [], open_positions: [] }
  hydrateCardForms(queue.value.closed_trades || [])
  hydratePositionForms(queue.value.open_positions || [])
  hydrateDailyReview(queue.value.daily_review)
  await loadQueuePretradeStatus()
  syncLabelTitleTargets()
}

function tradeStatusClass(status) {
  const value = (status || '').toLowerCase()
  if (value === 'closed') return 'badge-profit'
  if (value === 'open') return 'badge-loss'
  return 'badge-muted'
}

function missingItemBadgeClass(item) {
  if (['strategy', 'setup'].includes(item)) return 'badge-loss'
  if (['mistake_tags', 'screenshot'].includes(item)) return 'badge-warning'
  return 'badge'
}

async function openWorkspaceTab() {
  queueDate.value = pretradeDate.value
  journalTab.value = 'workspace'
  await loadQueue()
  syncLabelTitleTargets()
}

async function openPretradeTab() {
  pretradeDate.value = queueDate.value
  journalTab.value = 'pretrade'
  await loadPretrade()
  syncLabelTitleTargets()
}

async function openAnalyticsTab() {
  journalTab.value = 'analytics'
  await loadAnalytics()
  syncLabelTitleTargets()
}

async function saveCardReview(tradeGroupId) {
  const saveOk = await askConfirm({
    title: 'Save Trade Review',
    message: '确认保存这条 Trade Review 吗？',
    confirmText: 'Confirm Save',
    cancelText: 'Cancel',
  })
  if (!saveOk) return
  savingTrade.value = tradeGroupId
  try {
    const payload = { ...tradeReviewForms.value[tradeGroupId] }
    if (payload.plan_follow_take_again) {
      payload.would_take_again = payload.plan_follow_take_again
      payload.followed_plan = payload.plan_follow_take_again === 'yes'
    }
    delete payload.plan_follow_take_again
    const card = (queue.value.closed_trades || []).find((item) => item.trade_group_id === tradeGroupId)
    const selectedOpt = (card?.snapshot_options || []).find((opt) => Number(opt.id) === Number(payload.selected_snapshot))
    if (selectedOpt && !isCompatibleSymbol(selectedOpt.symbol, card?.symbol)) {
      const mismatchOk = await askConfirm({
        title: 'Linked Snapshot Mismatch',
        message: `所选 Snapshot 的 symbol(${selectedOpt.symbol || '-'}) 与交易 symbol(${card?.symbol || '-'}) 可能不一致，确认继续保存吗？`,
        confirmText: 'Continue Save',
        cancelText: 'Back',
      })
      if (!mismatchOk) return
      tradeSaveWarnings.value[tradeGroupId] = '已按确认结果继续保存 Linked Snapshot。若后端判定不匹配，关联可能不会生效。'
    } else {
      tradeSaveWarnings.value[tradeGroupId] = payload.selected_snapshot
        ? ''
        : '未关联 Linked Snapshot：本次允许保存，但建议后续补充以便计划对照分析。'
    }
    payload.entry_quality = normalizeScore(payload.entry_quality)
    payload.exit_quality = normalizeScore(payload.exit_quality)
    payload.risk_management = normalizeScore(payload.risk_management)
    await saveTradeReview(payload)
    tradeSaveErrors.value[tradeGroupId] = ''
    await loadQueue()
    showActionNotice('Trade Review 保存成功')
  } catch (error) {
    const data = error?.response?.data || {}
    tradeSaveErrors.value[tradeGroupId] = Object.entries(data)
      .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
      .join(' | ') || 'Save failed. Please check required fields.'
  } finally {
    savingTrade.value = null
  }
}


function isCompatibleSymbol(snapshotSymbol, tradeSymbol) {
  const left = String(snapshotSymbol || '').trim().toLowerCase()
  const right = String(tradeSymbol || '').trim().toLowerCase()
  if (!left || !right) return false
  return left === right || left.startsWith(right) || right.startsWith(left)
}

function normalizeScore(value) {
  if (value === '' || value == null) return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return Math.min(5, Math.max(1, Math.round(n)))
}

function buildLocalSnapshot(item = {}) {
  const parsedNotes = parseSnapshotNotes(item.snapshot_notes)
  const matchedSetupTag = (setupTags.value || []).find((tag) => Number(tag.id) === Number(item.setup))
  const mergedSetup = item.setup_type || matchedSetupTag?.name || ''
  return {
    local_id: item.id || `${Date.now()}-${Math.random()}`,
    id: item.id || null,
    pretrade_plan: item.pretrade_plan || pretradeForm.value.id,
    trade_group: item.trade_group || null,
    symbol: item.symbol || '',
    strategy: item.strategy || '',
    direction: item.direction || 'long',
    setup_type: item.setup_type || 'breakout',
    setup_merged: mergedSetup,
    timeframe: item.timeframe || '5m',
    confidence_score: item.confidence_score,
    setup: item.setup || null,
    trigger_type: item.trigger_type || 'custom',
    trigger_condition: item.trigger_condition || '',
    invalidation_type: item.invalidation_type || 'custom',
    invalidation: item.invalidation || '',
    planned_entry: item.planned_entry,
    planned_stop: item.planned_stop,
    planned_target: item.planned_target,
    planned_risk_r: item.planned_risk_r,
    trading_mode: parsedNotes.trading_mode || 'planned',
    entry_reason: parsedNotes.entry_reason || '',
    stop_logic: parsedNotes.stop_logic || '',
    checklist_passed: item.checklist_passed ?? false,
    snapshot_notes: item.snapshot_notes || '',
  }
}

async function loadPretrade() {
  const res = await fetchPretradePlans({ date: pretradeDate.value, page_size: 1 })
  const existing = (res.data?.results || res.data || [])[0]
  if (existing) {
    pretradeForm.value = { ...existing }
    pretradeSessions.value = (existing.session || 'premarket').split(',').map((v) => v.trim()).filter(Boolean)
    if (!pretradeSessions.value.length) pretradeSessions.value = ['premarket']
    watchlistText.value = (existing.watchlist || []).join(', ')
    pretradeChecklist.value = { market_trending: false, volume_above_average: false, no_major_news_risk: false, clean_structure: false, ...(existing.pre_trade_checklist || {}) }
    const snaps = await fetchSetupSnapshots({ pretrade_plan: existing.id, page_size: 50 })
    snapshotForms.value = (snaps.data?.results || snaps.data || []).map((item) => buildLocalSnapshot(item))
    expandedSnapshotCards.value = snapshotForms.value.map((row) => row.local_id)
  } else {
    pretradeForm.value = { id: null, plan_date: pretradeDate.value, session: 'premarket', market_regime: '', watchlist: [], catalysts: '', game_plan: '', pre_trade_checklist: {}, risk_budget_r: null, notes: '' }
    pretradeSessions.value = ['premarket']
    watchlistText.value = ''
    pretradeChecklist.value = { market_trending: false, volume_above_average: false, no_major_news_risk: false, clean_structure: false }
    snapshotForms.value = [buildLocalSnapshot()]
    expandedSnapshotCards.value = snapshotForms.value.map((row) => row.local_id)
  }
  syncLabelTitleTargets()
}

async function savePretrade(withConfirm = true) {
  if (withConfirm) {
    const ok = await askConfirm({
      title: 'Save Pre-Trade Plan',
      message: '确认保存 Pre-Trade Plan 吗？',
      confirmText: 'Confirm Save',
      cancelText: 'Cancel',
    })
    if (!ok) return
  }
  savingPretrade.value = true
  try {
    pretradeSubmitAttempted.value = true
    pretradeError.value = ''
    if (!pretradeForm.value.market_regime) {
      pretradeError.value = 'Market regime is required.'
      return
    }
    if (!(Number(pretradeForm.value.risk_budget_r) > 0)) {
      pretradeError.value = 'Risk budget (R) must be greater than 0.'
      return
    }
    if (!snapshotForms.value.length) {
      pretradeError.value = 'At least 1 setup snapshot is required.'
      return
    }
    const payload = {
      ...pretradeForm.value,
      session: (pretradeSessions.value || []).join(','),
      plan_date: pretradeDate.value,
      watchlist: watchlistText.value.split(',').map((v) => v.trim()).filter(Boolean),
      pre_trade_checklist: { ...pretradeChecklist.value },
    }
    const res = pretradeForm.value.id ? await updatePretradePlan(pretradeForm.value.id, payload) : await savePretradePlan(payload)
    pretradeForm.value = res.data
    if (!snapshotForms.value.length) snapshotForms.value = [buildLocalSnapshot()]
    showActionNotice('Pre-Trade Plan 保存成功')
  } finally {
    savingPretrade.value = false
  }
}

function addSnapshotRow() {
  const nextRow = buildLocalSnapshot()
  snapshotForms.value.push(nextRow)
  expandedSnapshotCards.value = [...expandedSnapshotCards.value, nextRow.local_id]
}

async function removeSnapshotRow(row) {
  const ok = await askConfirm({
    title: 'Delete Snapshot',
    message: '确认删除这个 Snapshot 吗？此操作不可撤销。',
    confirmText: 'Delete',
    cancelText: 'Cancel',
  })
  if (!ok) return
  if (row.id) await deleteSetupSnapshot(row.id)
  snapshotForms.value = snapshotForms.value.filter((item) => item.local_id !== row.local_id)
  expandedSnapshotCards.value = expandedSnapshotCards.value.filter((id) => id !== row.local_id)
  if (!snapshotForms.value.length) snapshotForms.value = [buildLocalSnapshot()]
  if (snapshotForms.value.length && !expandedSnapshotCards.value.length) {
    expandedSnapshotCards.value = snapshotForms.value.map((item) => item.local_id)
  }
  showActionNotice('Snapshot 删除成功')
}

async function removeLastSnapshotRow() {
  if (!snapshotForms.value.length) return
  const target = snapshotForms.value[snapshotForms.value.length - 1]
  await removeSnapshotRow(target)
}

async function saveSnapshot(row) {
  const ok = await askConfirm({
    title: 'Save Snapshot',
    message: '确认保存这个 Snapshot 吗？',
    confirmText: 'Confirm Save',
    cancelText: 'Cancel',
  })
  if (!ok) return
  snapshotSubmitAttempted.value = { ...snapshotSubmitAttempted.value, [row.local_id]: true }
  if (!pretradeForm.value.id) await savePretrade(false)
  if (!pretradeForm.value.id) return
  snapshotErrors.value[row.local_id] = ''
  if (!(Number(row.planned_risk_r) > 0)) {
    snapshotErrors.value[row.local_id] = 'Planned risk (R) is required and must be greater than 0.'
    return
  }
  const otherRowsRisk = snapshotForms.value
    .filter((item) => item.local_id !== row.local_id)
    .reduce((sum, item) => sum + Number(item.planned_risk_r || 0), 0)
  const nextUsed = otherRowsRisk + Number(row.planned_risk_r || 0)
  const budget = Number(pretradeForm.value.risk_budget_r || 0)
  if (budget > 0 && nextUsed > budget) {
    snapshotErrors.value[row.local_id] = `Planned risk would exceed budget (${nextUsed.toFixed(2)}R / ${budget.toFixed(2)}R).`
    return
  }
  if (!row.symbol || !String(row.setup_merged || '').trim()) {
    snapshotErrors.value[row.local_id] = 'Symbol and Setup are required.'
    return
  }
  if (row.trading_mode !== 'reactive' && (row.planned_entry == null || row.planned_stop == null || row.planned_target == null)) {
    snapshotErrors.value[row.local_id] = 'For Planned Trade mode, entry, stop, target, and planned risk are required.'
    return
  }
  savingSnapshotId.value = row.local_id
  try {
    const payload = { ...row, pretrade_plan: pretradeForm.value.id }
    const setupMatch = (setupTags.value || []).find((item) => String(item.name || '').toLowerCase() === String(row.setup_merged || '').trim().toLowerCase())
    payload.setup = setupMatch ? setupMatch.id : null
    payload.setup_type = String(row.setup_merged || '').trim()
    payload.snapshot_notes = toSnapshotNotes(row)
    if (row.trading_mode === 'reactive') payload.planned_entry = null
    delete payload.setup_merged
    delete payload.trading_mode
    delete payload.entry_reason
    delete payload.stop_logic
    delete payload.local_id
    const res = row.id ? await updateSetupSnapshot(row.id, payload) : await saveSetupSnapshot(payload)
    Object.assign(row, buildLocalSnapshot(res.data))
    showActionNotice('Snapshot 保存成功')
  } finally {
    savingSnapshotId.value = null
  }
}

const usedRiskR = computed(() => snapshotForms.value.reduce((sum, row) => sum + Number(row.planned_risk_r || 0), 0))

const remainingRiskR = computed(() => {
  const budget = Number(pretradeForm.value.risk_budget_r || 0)
  return budget - usedRiskR.value
})
const usedRiskPct = computed(() => {
  const budget = Number(pretradeForm.value.risk_budget_r || 0)
  if (!(budget > 0)) return 0
  return Math.min(100, Math.max(0, (usedRiskR.value / budget) * 100))
})
const riskLimitReached = computed(() => remainingRiskR.value <= 0)
const riskStatusClass = computed(() => {
  if (usedRiskPct.value >= 100) return 'risk-danger'
  if (usedRiskPct.value >= 75) return 'risk-warning'
  return 'risk-safe'
})
const checklistKeys = ['market_trending', 'volume_above_average', 'no_major_news_risk', 'clean_structure']
const checklistTotal = checklistKeys.length
const checklistPassCount = computed(() => checklistKeys.reduce((sum, key) => sum + (pretradeChecklist.value[key] ? 1 : 0), 0))
const pretradeChecklistPassed = computed(() => checklistPassCount.value === checklistTotal)

function snapshotIsComplete(row) {
  const hasBasics = Boolean(row.symbol && String(row.setup_merged || '').trim() && Number(row.planned_risk_r || 0) > 0)
  if (!hasBasics) return false
  if (row.trading_mode === 'reactive') return true
  return row.planned_entry != null && row.planned_stop != null && row.planned_target != null
}

async function loadQueuePretradeStatus() {
  const res = await fetchPretradePlans({ date: queueDate.value, page_size: 1 })
  const plan = (res.data?.results || res.data || [])[0]
  queuePretradePlan.value = plan || null
  if (plan) {
    if (!form.value.market_regime) form.value.market_regime = plan.market_regime || ''
    if (!form.value.daily_bias) form.value.daily_bias = plan.daily_bias || plan.session || ''
  }
  if (!plan || !plan.market_regime || !(Number(plan.risk_budget_r) > 0)) {
    queuePretradeReady.value = false
    queuePretradeMessage.value = 'Complete Pre-Trade Plan (market regime + risk budget + snapshots) before Start Review.'
    return
  }
  const snaps = await fetchSetupSnapshots({ pretrade_plan: plan.id, page_size: 50 })
  const rows = (snaps.data?.results || snaps.data || [])
  if (!rows.length || !rows.every(snapshotIsComplete)) {
    queuePretradeReady.value = false
    queuePretradeMessage.value = 'At least one complete setup snapshot is required before Start Review.'
    return
  }
  queuePretradeReady.value = true
  queuePretradeMessage.value = ''
}

async function loadAnalytics() {
  loadingAnalytics.value = true
  try {
    analyticsError.value = ''
    const res = await fetchTradeReviewAnalyticsSummary()
    analytics.value = res.data || { by_strategy: [], by_session: [], by_symbol: [], strategy_edge_ranking: [], mistake_impact: [], plan_adherence: {}, insights: [] }
    const keys = (analytics.value[compareDimension.value] || []).map((row) => row.key)
    compareLeftKey.value = keys[0] || ''
    compareRightKey.value = keys[1] || keys[0] || ''
  } catch (error) {
    analyticsError.value = error?.response?.data?.detail || 'Failed to load analytics.'
  } finally {
    loadingAnalytics.value = false
  }
}

async function uploadTradeScreenshots(tradeGroupId, event) {
  const files = event?.target?.files
  if (!files?.length) return
  uploadingTrade.value = tradeGroupId
  try {
    const res = await uploadDailyReviewImages(files)
    const urls = res.data?.image_urls || (res.data?.image_url ? [res.data.image_url] : [])
    const prev = tradeReviewForms.value[tradeGroupId].screenshots || []
    tradeReviewForms.value[tradeGroupId].screenshots = [...prev, ...urls]
  } finally {
    uploadingTrade.value = null
    if (event?.target) event.target.value = ''
  }
}

function removeTradeScreenshot(tradeGroupId, index) {
  askConfirm({
    title: 'Delete Screenshot',
    message: '确认删除这张截图吗？',
    confirmText: 'Delete',
    cancelText: 'Cancel',
  }).then((ok) => {
    if (!ok) return
    const arr = [...(tradeReviewForms.value[tradeGroupId].screenshots || [])]
    arr.splice(index, 1)
    tradeReviewForms.value[tradeGroupId].screenshots = arr
    showActionNotice('截图删除成功')
  })
}

async function saveCheckpoint(tradeGroupId) {
  const ok = await askConfirm({
    title: 'Save Checkpoint',
    message: '确认保存这个 Position Checkpoint 吗？',
    confirmText: 'Confirm Save',
    cancelText: 'Cancel',
  })
  if (!ok) return
  savingPosition.value = tradeGroupId
  try {
    await savePositionCheckpoint({ ...positionForms.value[tradeGroupId] })
    await loadQueue()
    showActionNotice('Checkpoint 保存成功')
  } finally {
    savingPosition.value = null
  }
}

async function uploadDailyScreenshots(event) {
  const files = event?.target?.files
  if (!files?.length) return
  uploadingDailyImage.value = true
  try {
    const res = await uploadDailyReviewImages(files)
    const urls = res.data?.image_urls || (res.data?.image_url ? [res.data.image_url] : [])
    form.value.image_urls = [...(form.value.image_urls || []), ...urls]
  } finally {
    uploadingDailyImage.value = false
    if (event?.target) event.target.value = ''
  }
}

function removeDailyScreenshot(index) {
  askConfirm({
    title: 'Delete Screenshot',
    message: '确认删除这张截图吗？',
    confirmText: 'Delete',
    cancelText: 'Cancel',
  }).then((ok) => {
    if (!ok) return
    const arr = [...(form.value.image_urls || [])]
    arr.splice(index, 1)
    form.value.image_urls = arr
    showActionNotice('截图删除成功')
  })
}

async function saveDailyReview(mode = 'draft') {
  const ok = await askConfirm({
    title: mode === 'completed' ? 'Mark Complete' : 'Save Draft',
    message: mode === 'completed' ? '确认保存并标记为 Completed 吗？' : '确认保存 Daily Review 草稿吗？',
    confirmText: 'Confirm Save',
    cancelText: 'Cancel',
  })
  if (!ok) return
  savingDaily.value = true
  try {
    const payload = { ...form.value, review_date: queueDate.value }
    payload.review_status = mode
    payload.max_daily_loss_respected = maxLossSelection.value === '' ? null : maxLossSelection.value === 'true'
    payload.market_behaved_as_expected = marketExpectedSelection.value === '' ? null : marketExpectedSelection.value === 'true'
    await createDailyReview(payload)
    await loadQueue()
    showActionNotice(mode === 'completed' ? 'Daily Review 标记完成成功' : 'Daily Review 草稿保存成功')
  } finally {
    savingDaily.value = false
  }
}

function focusFirstPending() {
  if ((queue.value.closed_trades || []).length) {
    tradeSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  if (!queue.value.summary.daily_review_completed) {
    dailySectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  positionSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(async () => {
  document.addEventListener('click', handleDocumentClick)
  await loadMetaTags()
  await loadQueue()
  await loadPretrade()
  await loadAnalytics()
  syncLabelTitleTargets()
  nextTick(() => focusFirstPending())
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  if (actionNoticeTimer) clearTimeout(actionNoticeTimer)
})
</script>

<style scoped>
.action-toast {
  position: sticky;
  top: 10px;
  z-index: 50;
  width: fit-content;
  margin: 0 auto 10px;
  padding: 8px 12px;
  border-radius: 10px;
  background: #ecfdf5;
  color: #166534;
  border: 1px solid #86efac;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
  font-weight: 600;
}

.workspace-summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 220px));
  gap: 10px 14px;
  align-items: stretch;
}

.review-workspace-page {
  background: #f7f8fa;
  padding-bottom: 16px;
}

.workspace-summary-card,
.workspace-primary-card,
.workspace-secondary-card,
.workspace-tertiary-card {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
}

.workspace-review-cluster {
  margin-top: 12px;
  padding: 14px;
}

.workspace-review-cluster > .card + .card {
  margin-top: 14px;
}

.workspace-primary-card {
  border-color: #bfdbfe;
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.15);
}

.workspace-secondary-card {
  background: #f8fafc;
}

.workspace-tertiary-card {
  background: #fafafa;
  opacity: 0.96;
}

.workspace-summary-card .stat-pill {
  background: #ffffff;
  border: 1px solid #dbe3f4;
  border-radius: 10px;
  padding: 10px 12px;
  min-height: 96px;
  display: grid;
  align-content: start;
  gap: 6px;
  overflow: hidden;
}

.summary-pretrade-note {
  white-space: nowrap;
}

.queue-date-pill {
  gap: 8px;
}

.queue-date-input {
  width: 100%;
}

.workspace-summary-card .stat-value {
  font-size: 30px;
  font-weight: 700;
}

.workspace-summary-card .stat-label {
  color: #64748b;
}

.completion-summary-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tv-panel-tabs .tv-subtab {
  background: #ffffff;
  border-radius: 10px;
  border: 1px solid #dbe3f4;
  color: #64748b;
  padding: 8px 14px;
  font-weight: 600;
  cursor: pointer;
}

.tv-panel-tabs .tv-subtab.active {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.1);
}

.tv-panel-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  background: #f8fbff;
}

.review-workspace-page :deep(button.secondary),
.review-workspace-page :deep(.secondary.small-btn) {
  background: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
}

.review-workspace-page :deep(button.secondary:hover),
.review-workspace-page :deep(.secondary.small-btn:hover) {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.trade-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 12px;
}

.trade-review-card {
  margin-bottom: 0;
  padding: 14px;
}

.trade-review-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.review-head-main {
  display: grid;
  gap: 8px;
}

.review-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.summary-chip-row .badge {
  font-weight: 700;
  letter-spacing: 0.02em;
}

.trade-review-progress {
  min-width: 72px;
  display: grid;
  gap: 4px;
  align-content: start;
}

.trade-review-percent {
  text-align: right;
}

.trade-review-actions {
  margin-top: 8px;
}

.compact-trade-body {
  padding-top: 10px;
}

.trade-review-form-grid {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px 10px;
  margin-bottom: 10px;
}

.trade-review-text-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px 10px;
}

.workspace-field-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 320px));
  gap: 10px 16px;
}

.workspace-field-grid label,
.workspace-summary-grid label {
  gap: 6px;
}

.pretrade-module-card {
  margin-top: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
  padding: 14px;
}

.snapshot-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.pretrade-textarea-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px 12px;
}

.pretrade-checklist-grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, max-content));
  justify-content: start;
  gap: 6px 8px;
}

.checklist-item {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  padding: 6px 10px;
  width: max-content;
  max-width: 100%;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.check-on {
  background: #ecfdf5;
  color: #166534;
  border-color: #86efac;
}

.check-off {
  background: #fef2f2;
  color: #b91c1c;
  border-color: #fca5a5;
}

.workspace-field-grid :deep(input),
.workspace-field-grid :deep(select),
.workspace-summary-grid :deep(input),
.trade-review-form-grid :deep(input),
.trade-review-form-grid :deep(select),
.trade-review-text-grid :deep(textarea) {
  padding: 8px 10px;
}

.workspace-field-grid :deep(input[type='checkbox']),
.workspace-field-grid :deep(input[type='radio']),
.workspace-summary-grid :deep(input[type='checkbox']),
.workspace-summary-grid :deep(input[type='radio']),
.trade-review-form-grid :deep(input[type='checkbox']),
.trade-review-form-grid :deep(input[type='radio']) {
  padding: 0;
}

.multi-select-wrap {
  position: relative;
}

.multi-select-trigger {
  width: 100%;
  text-align: left;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  padding: 8px 10px;
  color: #111827;
}

.multi-select-panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 30;
  background: #fff;
  border: 1px solid #dbe3f4;
  border-radius: 10px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.15);
  padding: 8px;
  display: grid;
  gap: 6px;
}

.multi-select-option {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
}

.multi-select-option :deep(input[type='checkbox']),
.checklist-item :deep(input[type='checkbox']) {
  width: auto;
  min-width: 14px;
  height: 14px;
  padding: 0;
  margin: 0;
  border-radius: 3px;
  flex: 0 0 auto;
}

.trading-mode-switch {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.mode-option {
  display: inline-flex !important;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.mode-option :deep(input[type='radio']) {
  width: auto;
  margin: 0;
  padding: 0;
}

.trade-review-text-grid :deep(textarea) {
  min-height: 72px;
}

.metric-with-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.metric-tip {
  position: absolute;
  left: 0;
  top: calc(100% + 6px);
  z-index: 20;
  min-width: 200px;
  max-width: 280px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 12px;
  line-height: 1.35;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.25);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-2px);
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.metric-with-tip:hover .metric-tip {
  opacity: 1;
  transform: translateY(0);
}

.save-error {
  margin-top: 8px;
  color: #b91c1c;
  font-size: 12px;
}

.save-warning {
  margin-top: 8px;
  color: #92400e;
  font-size: 12px;
}

.required-asterisk {
  color: #dc2626;
  font-weight: 700;
}

.field-missing {
  border-color: #dc2626 !important;
  box-shadow: 0 0 0 1px rgba(220, 38, 38, 0.15);
}

.field-missing::placeholder {
  color: #dc2626;
  opacity: 1;
}

.confirm-modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.confirm-modal-card {
  width: min(520px, 92vw);
  background: #ffffff;
  border: 1px solid #dbe3f4;
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.2);
  padding: 16px;
}

.badge-warning {
  background: #fef3c7;
  color: #92400e;
}

.risk-dashboard {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(90px, max-content));
  justify-content: start;
  gap: 4px 12px;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #d1d5db;
}

.risk-dashboard > :first-child {
  margin-right: 8px;
}

.risk-progress {
  grid-column: 1 / -1;
}

.risk-safe {
  background: #ecfdf5;
  border-color: #86efac;
}

.risk-warning {
  background: #fffbeb;
  border-color: #fde68a;
}

.risk-danger {
  background: #fef2f2;
  border-color: #fca5a5;
}

.status-good,
.status-good-block {
  color: #166534;
}

.status-bad,
.status-bad-block {
  color: #b91c1c;
}

.status-good-block,
.status-bad-block {
  margin-top: 6px;
  padding: 6px 10px;
  width: fit-content;
  min-width: 140px;
  border-radius: 8px;
  border: 1px solid transparent;
}

.status-good-block {
  background: #ecfdf5;
  border-color: #86efac;
}

.status-bad-block {
  background: #fef2f2;
  border-color: #fca5a5;
}

.risk-progress {
  grid-column: 1 / -1;
  height: 18px;
  border-radius: 999px;
  background: #e5e7eb;
  overflow: hidden;
}

.risk-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #f59e0b, #ef4444);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 44px;
  padding-right: 8px;
}

.risk-progress-label {
  font-size: 11px;
  font-weight: 700;
  color: #ffffff;
  text-shadow: 0 1px 2px rgba(15, 23, 42, 0.45);
}

.logic-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.analytics-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.analytics-surface {
  background: #f8fafc;
}

.analytics-panel-card {
  border: 1px solid #dbe3f4;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
}

.kpi-card {
  border: 1px solid #dbe3f4;
  border-radius: 10px;
  background: #f8fafc;
  padding: 10px;
}

.kpi-label {
  font-size: 12px;
  color: #64748b;
}

.kpi-value {
  margin-top: 4px;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}

.kpi-positive {
  color: #15803d;
}

.kpi-negative {
  color: #b91c1c;
}

.insight-highlight-card {
  margin-top: 10px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  border-radius: 10px;
  padding: 10px 12px;
}

.analytics-table-wrap {
  overflow-x: auto;
}

.analytics-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.analytics-table th,
.analytics-table td {
  border-bottom: 1px solid #e5e7eb;
  padding: 8px 10px;
  text-align: left;
}

.analytics-plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}

.analytics-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 6px 0;
}

.review-pnl-pill {
  font-size: 18px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
}

.pnl-positive {
  background: #ecfdf5;
  color: #166534;
}

.pnl-negative {
  background: #fef2f2;
  color: #b91c1c;
}

.reflection-box {
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 8px 10px;
}

.reflection-title {
  font-weight: 700;
  margin-bottom: 4px;
}

.reflection-good {
  background: #f0fdf4;
}

.reflection-bad {
  background: #fef2f2;
}

.badge-muted {
  background: #e5e7eb;
  color: #374151;
}

@media (max-width: 900px) {
  .trade-card-grid,
  .workspace-summary-grid,
  .workspace-field-grid {
    grid-template-columns: 1fr;
  }
}
</style>
