<template>
  <div class="decision-journal">
    <div class="dashboard-hero card journal-hero">
      <div>
        <div class="dashboard-kicker">{{ t('decisionLifecycle') }}</div>
        <h1 class="dashboard-title">{{ t('journalTitle') }}</h1>
        <p class="dashboard-subtitle">{{ t('journalSubtitle') }}</p>
      </div>
      <div class="journal-hero-tools">
        <div class="language-switch" role="group" :aria-label="t('language')">
          <button :class="{ active: language === 'zh' }" @click="setLanguage('zh')">中文</button>
          <button :class="{ active: language === 'en' }" @click="setLanguage('en')">English</button>
        </div>
        <div class="journal-date-control">
          <span>{{ t('tradingDay') }}</span>
          <input v-model="selectedDate" type="date" @change="loadToday" />
        </div>
      </div>
    </div>

    <div class="journal-tabs card">
      <button v-for="item in tabs" :key="item.id" :class="['tv-subtab', { active: activeTab === item.id }]" @click="selectTab(item.id)">
        {{ t(item.labelKey) }}
      </button>
    </div>

    <div v-if="loading" class="card">{{ t('loadingJournal') }}</div>

    <template v-else-if="activeTab === 'today'">
      <div v-if="!tradingDay" class="card journal-empty-state">
        <div>
          <div class="section-title">{{ t('startDay') }} {{ selectedDate }}</div>
          <p class="muted-copy">{{ t('startDayHelp') }}</p>
        </div>
        <div class="journal-form-grid three-col">
          <label><span>{{ t('dailyRiskLimit') }}</span><input v-model.number="dayForm.daily_risk_limit" type="number" min="0" step="10" /></label>
          <label><span>{{ t('maximumCampaigns') }}</span><input v-model.number="dayForm.max_trades" type="number" min="1" /></label>
          <label><span>{{ t('marketEnvironment') }}</span><input v-model.trim="dayForm.market_environment" :placeholder="t('marketEnvironmentPlaceholder')" /></label>
        </div>
        <button @click="createDay">{{ t('createTradingDay') }}</button>
      </div>

      <template v-else>
        <div class="journal-risk-strip">
          <div class="card risk-cell"><span>{{ t('dayStatus') }}</span><strong>{{ enumLabel(tradingDay.status) }}</strong></div>
          <div class="card risk-cell"><span>{{ t('netPnl') }}</span><strong :class="numberClass(tradingDay.realized_pnl)">{{ money(tradingDay.realized_pnl) }}</strong></div>
          <div class="card risk-cell"><span>{{ t('totalR') }}</span><strong :class="numberClass(tradingDay.total_r)">{{ number(tradingDay.total_r) }}R</strong></div>
          <div class="card risk-cell"><span>{{ t('campaigns') }}</span><strong>{{ tradingDay.campaign_count }}</strong></div>
          <div class="card risk-cell"><span>{{ t('attempts') }}</span><strong>{{ tradingDay.attempt_count }}</strong></div>
          <div class="card risk-cell"><span>{{ t('riskBudget') }}</span><strong>{{ tradingDay.daily_risk_limit ? money(tradingDay.daily_risk_limit) : t('notSet') }}</strong></div>
        </div>

        <div class="journal-workspace-grid">
          <section class="journal-column">
            <div class="column-heading">
              <div><div class="section-title">{{ t('decisionContexts') }}</div><span class="muted-copy">{{ t('decisionContextsHelp') }}</span></div>
              <button class="secondary small-btn" @click="showSessionForm = !showSessionForm">{{ showSessionForm ? t('cancel') : t('newContext') }}</button>
            </div>

            <form v-if="showSessionForm" class="card inline-journal-form" @submit.prevent="createSession">
              <label><span>{{ t('contextKind') }}</span><select v-model="sessionForm.context_kind" @change="syncContextType"><option value="intraday">{{ t('intradayContext') }}</option><option value="swing">{{ t('swingContext') }}</option></select></label>
              <label><span>{{ t('name') }}</span><input v-model.trim="sessionForm.name" required :placeholder="t('openingSession')" /></label>
              <label><span>{{ sessionForm.context_kind === 'swing' ? t('positionStage') : t('timeSegment') }}</span><select v-model="sessionForm.context_type"><option v-for="item in sessionForm.context_kind === 'swing' ? positionStages : sessionTypes" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
              <label><span>{{ t('riskLimitR') }}</span><input v-model.number="sessionForm.risk_limit_r" type="number" min="0" step="0.25" /></label>
              <label><span>{{ t('environment') }}</span><input v-model.trim="sessionForm.market_environment" :placeholder="t('volatileTrend')" /></label>
              <label class="wide"><span>{{ t('allowedSetups') }}</span><input v-model.trim="sessionForm.allowed_setups_text" :placeholder="t('setupExamples')" /></label>
              <label class="wide"><span>{{ t('noTradeConditions') }}</span><input v-model.trim="sessionForm.no_trade_conditions" :placeholder="t('noTradePlaceholder')" /></label>
              <button :disabled="saving">{{ t('createContext') }}</button>
            </form>

            <div class="context-card-grid">
            <div v-if="!contexts.length" class="card empty-row">{{ t('noContexts') }}</div>
            <article v-for="session in contexts" :key="session.id" :class="['card', 'session-card', { selected: selectedSessionId === session.id }]" @click="selectedSessionId = session.id">
              <div class="card-title-row">
                <div><strong>{{ session.name }}</strong><div class="muted-copy">{{ enumLabel(session.context_kind) }} · {{ enumLabel(session.context_type) }} · {{ session.market_environment || t('environmentNotSet') }}</div></div>
                <span :class="['badge', statusClass(session.status)]">{{ enumLabel(session.status) }}</span>
              </div>
              <div class="session-metrics"><span>{{ session.campaign_count }} {{ t('campaignsLower') }}</span><span>{{ number(session.result_r) }}R</span><span>{{ t('limit') }} {{ session.risk_limit_r || '-' }}R</span></div>
              <div class="row-actions">
                <button v-if="session.status === 'planned'" class="secondary small-btn" @click.stop="startSession(session)">{{ t('start') }}</button>
                <button v-if="session.status === 'active'" class="secondary small-btn" @click.stop="closeSession(session)">{{ t('close') }}</button>
                <button class="secondary small-btn" @click.stop="openCampaignForm(session.id)">{{ t('newDecision') }}</button>
              </div>
            </article>
            </div>
          </section>

          <section class="journal-main-column">
            <div class="column-heading">
              <div><div class="section-title">{{ t('activeDecisions') }}</div><span class="muted-copy">{{ t('decisionsHelp') }}</span></div>
              <button v-if="contexts.length" @click="openCampaignForm(selectedSessionId || contexts[0].id)">{{ t('createCampaign') }}</button>
            </div>

            <form v-if="showCampaignForm" class="card campaign-builder" @submit.prevent="createCampaign(false)">
              <div class="builder-head"><div><strong>{{ editingCampaignId ? t('editDecisionVersion') : t('campaignSnapshot') }}</strong><span>{{ editingCampaignId ? t('versionSaveHelp') : t('preTradeEditableHelp') }}</span></div><button type="button" class="secondary small-btn" @click="showCampaignForm = false; editingCampaignId = ''">{{ t('close') }}</button></div>
              <div class="journal-form-grid four-col">
                <label><span>{{ t('decisionContext') }}</span><select v-model="campaignForm.context" required @change="syncHorizonToContext"><option v-for="item in contexts" :key="item.id" :value="item.id">{{ item.name }} · {{ enumLabel(item.context_type) }}</option></select></label>
                <label><span>{{ t('symbol') }}</span><input v-model.trim="campaignForm.symbol" required placeholder="MES" /></label>
                <label><span>{{ t('direction') }}</span><select v-model="campaignForm.direction"><option value="long">{{ enumLabel('long') }}</option><option value="short">{{ enumLabel('short') }}</option><option value="neutral">{{ enumLabel('neutral') }}</option></select></label>
                <label><span>{{ t('horizon') }}</span><select v-model="campaignForm.horizon"><option v-for="item in availableHorizons" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
                <label><span>{{ t('setup') }}</span><input v-model.trim="campaignForm.setup" required :placeholder="t('openingBreakout')" /></label>
                <label><span>{{ t('riskAmount') }}</span><input v-model.number="campaignForm.planned_risk_amount" required type="number" inputmode="decimal" min="0.01" step="0.01" /></label>
                <label><span>{{ t('maxRiskR') }}</span><input v-model.number="campaignForm.max_risk_r" required type="number" inputmode="decimal" min="0.01" step="0.01" /></label>
                <label><span>{{ t('maximumAttempts') }}</span><input v-model.number="campaignForm.max_attempts" required type="number" min="1" max="10" /></label>
              </div>
              <div class="journal-form-grid two-col">
                <label><span>{{ t('observedEvidence') }}</span><input v-model.trim="campaignForm.observed_evidence_text" required :placeholder="t('evidencePlaceholder')" /></label>
                <label><span>{{ t('interpretation') }}</span><input v-model.trim="campaignForm.interpretation" required :placeholder="t('interpretationPlaceholder')" /></label>
                <label><span>{{ t('strongestCounterCase') }}</span><input v-model.trim="campaignForm.strongest_counter_case" required :placeholder="t('counterCasePlaceholder')" /></label>
                <label><span>{{ t('chosenAction') }}</span><input v-model.trim="campaignForm.chosen_action" :placeholder="t('chosenActionPlaceholder')" /></label>
                <label><span>{{ t('entryTrigger') }}</span><input v-model.trim="campaignForm.entry_trigger" required :placeholder="t('entryTriggerPlaceholder')" /></label>
                <label><span>{{ t('invalidation') }}</span><input v-model.trim="campaignForm.invalidation" required :placeholder="t('invalidationPlaceholder')" /></label>
                <label><span>{{ t('timeStop') }}</span><input v-model.trim="campaignForm.time_stop" :placeholder="t('timeStopPlaceholder')" /></label>
                <label v-if="editingCampaignId"><span>{{ t('changeNote') }}</span><input v-model.trim="campaignForm.change_note" required :placeholder="t('changeNotePlaceholder')" /></label>
              </div>

              <div class="scenario-heading"><strong>{{ t('mutuallyExclusiveScenarios') }}</strong><span :class="['probability-total', { valid: probabilityValid }]">{{ t('total') }} {{ probabilityTotal }}%</span></div>
              <div class="scenario-grid">
                <div v-for="(scenario, index) in campaignForm.scenarios" :key="index" class="scenario-card">
                  <div class="scenario-card-head"><strong>{{ t('scenario') }} {{ index + 1 }}</strong><button v-if="campaignForm.scenarios.length > 2" type="button" class="text-button" @click="removeScenario(index)">{{ t('remove') }}</button></div>
                  <label><span>{{ t('name') }}</span><input v-model.trim="scenario.name" required :placeholder="t('scenarioNamePlaceholder')" /></label>
                  <label><span>{{ t('probability') }}</span><input v-model.number="scenario.probability" required type="number" min="1" max="99" step="1" /></label>
                  <label><span>{{ t('confirmation') }}</span><input v-model.trim="scenario.confirmation" required :placeholder="t('confirmationPlaceholder')" /></label>
                  <label><span>{{ t('contradiction') }}</span><input v-model.trim="scenario.contradiction" required :placeholder="t('contradictionPlaceholder')" /></label>
                  <label><span>{{ t('plannedAction') }}</span><input v-model.trim="scenario.planned_action" required :placeholder="t('plannedActionPlaceholder')" /></label>
                </div>
              </div>
              <button v-if="campaignForm.scenarios.length < 3" type="button" class="secondary small-btn" @click="addScenario">{{ t('addThirdScenario') }}</button>
              <div class="builder-actions">
                <button type="submit" class="secondary" :disabled="saving || !probabilityValid">{{ editingCampaignId ? t('saveNewVersion') : t('savePlanned') }}</button>
                <button v-if="!editingCampaignId" type="button" :disabled="saving || !probabilityValid" @click="createCampaign(true)">{{ t('saveAndActivate') }}</button>
              </div>
            </form>

            <div v-if="!todayCampaigns.length" class="card empty-row">{{ t('createDecisionFirst') }}</div>
            <article v-for="campaign in todayCampaigns" :key="campaign.id" class="card campaign-card">
              <div class="campaign-card-top">
                <div><strong>{{ campaign.symbol }} · {{ campaign.setup }}</strong><div class="muted-copy">{{ enumLabel(campaign.direction) }} · {{ enumLabel(campaign.horizon) }} · {{ campaign.context_name }} · {{ enumLabel(campaign.context_type) }}</div></div>
                <div class="campaign-badges"><span :class="['badge', phaseClass(campaign.lifecycle?.phase)]">{{ enumLabel(campaign.lifecycle?.phase) }}</span><span :class="['badge', statusClass(campaign.status)]">{{ enumLabel(campaign.status) }}</span></div>
              </div>
              <div class="campaign-stats">
                <span><small>{{ t('readiness') }}</small><strong>{{ campaign.readiness.score }}%</strong></span>
                <span><small>{{ t('risk') }}</small><strong>{{ campaign.max_risk_r }}R / {{ money(campaign.planned_risk_amount) }}</strong></span>
                <span><small>{{ t('result') }}</small><strong :class="numberClass(campaign.result_r)">{{ number(campaign.result_r) }}R</strong></span>
                <span><small>{{ t('attempts') }}</small><strong>{{ campaign.attempts.length }}/{{ campaign.max_attempts }}</strong></span>
              </div>
              <div v-if="campaign.current_decision" class="snapshot-summary">
                <div><span>{{ t('trigger') }}</span><strong>{{ campaign.current_decision.entry_trigger }}</strong></div>
                <div><span>{{ t('invalidation') }}</span><strong>{{ campaign.current_decision.invalidation }}</strong></div>
                <div class="scenario-chips"><span v-for="(scenario, index) in campaign.current_decision.scenarios" :key="scenario.id || index">{{ scenario.name }} {{ scenario.probability }}%</span></div>
                <code v-if="campaign.decision_snapshot">🔒 {{ campaign.decision_snapshot.immutable_snapshot_hash.slice(0, 12) }}…</code>
                <code v-else>{{ t('version') }} {{ campaign.lifecycle?.version_count }}</code>
              </div>
              <div class="row-actions">
                <button v-if="campaign.lifecycle?.can_edit_decision && campaign.current_decision" class="secondary small-btn" @click="editCampaign(campaign)">{{ t('editAndSaveVersion') }}</button>
                <button v-if="campaign.status === 'planned' && campaign.current_decision" class="secondary small-btn" @click="activateCampaign(campaign)">{{ t('activate') }}</button>
                <button v-if="campaign.lifecycle?.can_pause" class="secondary small-btn" @click="pauseCampaign(campaign)">{{ t('pauseCampaign') }}</button>
                <button v-if="campaign.lifecycle?.can_resume" class="secondary small-btn" @click="resumeCampaign(campaign)">{{ t('resumeCampaign') }}</button>
                <button v-if="campaign.lifecycle?.can_add_update" class="secondary small-btn" @click="openDecisionUpdate(campaign)">{{ t('decisionUpdate') }}</button>
                <button v-if="campaign.lifecycle?.can_close" class="secondary small-btn" @click="closeCampaign(campaign)">{{ t('closeCampaign') }}</button>
                <span v-else-if="campaign.lifecycle?.has_open_position" class="flow-hint">{{ t('closePositionFirst') }}</span>
                <button v-if="['review_pending', 'closed'].includes(campaign.status)" class="small-btn" @click="openReview(campaign)">{{ t('review') }}</button>
                <button v-if="campaign.lifecycle?.decision_locked" class="text-button correction-button" @click="openCorrection(campaign)">{{ t('recordCorrection') }}</button>
                <button v-if="campaign.lifecycle?.can_delete" class="text-button delete-button" @click="removeCampaign(campaign)">{{ t('deleteDirtyCampaign') }}</button>
              </div>
              <details v-if="campaign.decision_versions?.length" class="version-history"><summary>{{ t('versionHistory') }} · {{ campaign.decision_versions.length }}</summary><div v-for="versionItem in campaign.decision_versions" :key="versionItem.id" class="version-row"><strong>v{{ versionItem.version_no }}</strong><span>{{ shortDateTime(versionItem.created_at) }}</span><span>{{ versionItem.change_note || t('initialVersion') }}</span></div></details>
              <div v-if="campaign.attempts.length" class="attempt-list">
                <div v-for="attempt in campaign.attempts" :key="attempt.id" class="attempt-row">
                  <strong>#{{ attempt.sequence_no }}</strong><span>{{ enumLabel(attempt.status) }}</span><span>{{ attempt.fills.length }} {{ t('fillsLower') }}</span><span>{{ t('netPosition') }} <strong>{{ number(attempt.net_quantity) }}</strong></span><span :class="numberClass(attempt.result_r)">{{ number(attempt.result_r) }}R</span><button v-if="!attempt.fills.length" class="text-button delete-button" @click="removeAttempt(attempt)">{{ t('deleteEmptyAttempt') }}</button>
                </div>
              </div>
              <div v-if="campaign.decision_updates?.length" class="decision-update-list">
                <div v-for="update in campaign.decision_updates" :key="update.id" class="decision-update-row">
                  <span>{{ shortDateTime(update.event_at) }}</span><strong>{{ update.position_stage ? enumLabel(update.position_stage) : t('decisionUpdate') }}</strong><span>{{ enumLabel(update.event_type) }} · {{ update.decision }}</span>
                </div>
              </div>
              <div v-if="campaign.corrections?.length" class="correction-list"><div v-for="item in campaign.corrections" :key="item.id" class="correction-row"><strong>{{ t('correction') }} · {{ item.field_name }}</strong><span>{{ item.reason }}</span><small>{{ shortDateTime(item.created_at) }}</small></div></div>
              <form v-if="correctionCampaign?.id === campaign.id" class="decision-update-form correction-form" @submit.prevent="submitCorrection">
                <div class="journal-form-grid three-col">
                  <label><span>{{ t('correctionTarget') }}</span><select v-model="correctionForm.target_type"><option value="campaign">Campaign</option><option value="decision">{{ t('lockedDecision') }}</option><option value="execution">Execution</option><option value="review">{{ t('review') }}</option></select></label>
                  <label><span>{{ t('fieldName') }}</span><input v-model.trim="correctionForm.field_name" required /></label>
                  <label><span>{{ t('correctionReason') }}</span><input v-model.trim="correctionForm.reason" required /></label>
                  <label><span>{{ t('originalValue') }}</span><input v-model="correctionForm.original_value" /></label>
                  <label><span>{{ t('correctedValue') }}</span><input v-model="correctionForm.corrected_value" required /></label>
                </div>
                <div class="builder-actions"><button type="button" class="secondary" @click="correctionCampaign = null">{{ t('cancel') }}</button><button :disabled="saving">{{ t('saveCorrection') }}</button></div>
              </form>
            </article>
          </section>
        </div>

        <section class="card grouping-workspace">
          <div class="column-heading"><div><div class="section-title">{{ t('fillGrouping') }}</div><span class="muted-copy">{{ t('fillGroupingHelp') }}</span></div><span class="badge">{{ selectedFillIds.length }} {{ t('selected') }}</span></div>
          <div class="grouping-flow-guide"><strong>{{ t('groupingNextStep') }}</strong><span>{{ t('groupingNextStepHelp') }}</span></div>
          <div v-if="groupingError" class="grouping-error" role="alert"><strong>{{ t('groupingFailed') }}</strong><span>{{ groupingError }}</span><button class="secondary small-btn" @click="groupingError = ''; errorMessage = ''">{{ t('dismiss') }}</button></div>
          <div v-if="groupingResult" :class="['grouping-result', groupingResult.status === 'closed' ? 'complete' : 'open']">
            <div><strong>✓ {{ t('groupingSucceeded') }}</strong><span>{{ groupingResult.symbol }} · {{ t('attempt') }} #{{ groupingResult.sequenceNo }} · {{ groupingResult.fillCount }} {{ t('fillsLower') }}</span></div>
            <div class="grouping-result-metrics"><span>{{ t('netPosition') }} <strong>{{ number(groupingResult.netQuantity) }}</strong></span><span>{{ t('attemptStatus') }} <strong>{{ enumLabel(groupingResult.status) }}</strong></span></div>
            <p>{{ groupingResult.status === 'closed' ? t('groupingClosedNext') : t('groupingOpenNext') }}</p>
            <button class="secondary small-btn" @click="groupingResult = null">{{ t('dismiss') }}</button>
          </div>
          <div class="csv-import-row">
            <div><strong>{{ t('csvImport') }}</strong><span>{{ t('csvImportHelp') }}</span></div>
            <label class="csv-file-picker"><span>{{ t('chooseCsv') }}</span><input type="file" accept=".csv,text/csv" @change="importCsv" /></label>
          </div>
          <div class="grouping-controls">
            <label><span>{{ t('targetCampaign') }}</span><select v-model="groupingCampaignId" @change="syncGroupingAttemptTarget"><option value="">{{ t('selectCampaign') }}</option><option v-for="item in todayCampaigns" :key="item.id" :value="item.id">{{ item.symbol }} · {{ item.setup }}</option></select></label>
            <label><span>{{ t('targetAttempt') }}</span><select v-model="groupingAttemptId"><option value="">{{ t('createNewAttempt') }}</option><option v-for="item in groupingAttempts" :key="item.id" :value="item.id">{{ t('attempt') }} #{{ item.sequence_no }}</option></select></label>
            <label v-if="!groupingAttemptId"><span>{{ t('reentryReason') }}</span><select v-model="groupingForm.reentry_reason"><option value="">{{ t('firstEntry') }}</option><option v-for="item in reentryReasons" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label v-if="!groupingAttemptId"><span>{{ t('whatChanged') }}</span><input v-model.trim="groupingForm.what_changed" :placeholder="t('reentryRequired')" /></label>
            <button :disabled="!groupingCampaignId || !selectedFillIds.length || saving" @click="groupSelectedFills">{{ t('applyGrouping') }}</button>
            <button class="secondary" :disabled="!groupingCampaignId || saving" @click="undoGrouping">{{ t('undoGrouping') }}</button>
          </div>
          <div class="fill-view-tabs"><button v-for="item in ['ungrouped', 'grouped', 'all']" :key="item" :class="['secondary', 'small-btn', { active: fillView === item }]" @click="fillView = item">{{ t(`${item}Fills`) }}</button></div>
          <div class="tv-table-wrap">
            <table class="trade-table compact-fill-table">
              <thead><tr><th></th><th>{{ t('time') }}</th><th>{{ t('symbol') }}</th><th>{{ t('side') }}</th><th>{{ t('qty') }}</th><th>{{ t('price') }}</th><th>{{ t('currentGroup') }}</th></tr></thead>
              <tbody>
                <tr v-for="fill in displayedDayFills" :key="fill.id">
                  <td><input v-model="selectedFillIds" type="checkbox" :value="fill.id" /></td>
                  <td>{{ shortTime(fill.executed_at) }}</td><td>{{ fill.symbol }}</td><td>{{ enumLabel(fill.side) }}</td><td>{{ number(fill.quantity) }}</td><td>{{ number(fill.price) }}</td><td>{{ fill.location }}</td>
                </tr>
                <tr v-if="!displayedDayFills.length"><td colspan="7" class="empty-row">{{ fillView === 'ungrouped' ? t('noUngroupedFills') : t('noFills') }}</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="reviewQueue.length" class="card review-queue">
          <div class="section-title">{{ t('reviewQueue') }}</div>
          <div class="review-queue-grid"><button v-for="campaign in reviewQueue" :key="campaign.id" class="review-queue-item" @click="openReview(campaign)"><strong>{{ campaign.symbol }} · {{ campaign.setup }}</strong><span>{{ number(campaign.result_r) }}R · {{ campaign.attempts.length }} {{ t('attemptsLower') }}</span></button></div>
        </section>

        <form v-if="reviewCampaign" class="card review-form" @submit.prevent="submitReview">
          <div class="builder-head"><div><strong>{{ t('campaignReview') }} · {{ reviewCampaign.symbol }}</strong><span>{{ t('campaignReviewHelp') }}</span></div><button type="button" class="secondary small-btn" @click="reviewCampaign = null">{{ t('close') }}</button></div>
          <div class="review-result-strip"><span>{{ t('result') }} <strong>{{ number(reviewCampaign.result_r) }}R</strong></span><span>P&amp;L <strong>{{ money(reviewCampaign.realized_pnl) }}</strong></span><span>{{ t('attempts') }} <strong>{{ reviewCampaign.attempts.length }}</strong></span></div>
          <div class="journal-form-grid four-col">
            <label><span>{{ t('exitReason') }}</span><select v-model="reviewForm.exit_reason" required><option v-for="item in exitReasons" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label><span>{{ t('actualScenario') }}</span><select v-model="reviewForm.actual_scenario"><option value="">{{ t('unclear') }}</option><option v-for="item in reviewCampaign.decision_snapshot?.scenarios || []" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
            <label><span>{{ t('decisionGrade') }}</span><select v-model="reviewForm.decision_grade"><option v-for="item in grades" :key="item">{{ item }}</option></select></label>
            <label><span>{{ t('executionGrade') }}</span><select v-model="reviewForm.execution_grade"><option v-for="item in grades" :key="item">{{ item }}</option></select></label>
            <label><span>{{ t('entryFollowed') }}</span><select v-model="reviewForm.entry_followed"><option v-for="item in planChoices" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label><span>{{ t('managementFollowed') }}</span><select v-model="reviewForm.management_followed"><option v-for="item in planChoices" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label><span>{{ t('exitFollowed') }}</span><select v-model="reviewForm.exit_followed"><option v-for="item in planChoices" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label><span>{{ t('wouldRepeat') }}</span><select v-model="reviewForm.would_repeat"><option :value="true">{{ t('yes') }}</option><option :value="false">{{ t('no') }}</option></select></label>
          </div>
          <div class="journal-form-grid two-col">
            <label><span>{{ t('outcomeDrivers') }}</span><input v-model.trim="reviewForm.outcome_drivers_text" required /></label>
            <label><span>{{ t('knowableThen') }}</span><input v-model.trim="reviewForm.hindsight_known_then" required /></label>
            <label><span>{{ t('luckVariance') }}</span><input v-model.trim="reviewForm.hindsight_luck" required /></label>
            <label><span>{{ t('processChange') }}</span><input v-model.trim="reviewForm.hindsight_process" required /></label>
            <label class="wide"><span>{{ t('oneLesson') }}</span><input v-model.trim="reviewForm.lesson" required :placeholder="t('lessonPlaceholder')" /></label>
          </div>
          <button :disabled="saving">{{ t('submitReview') }}</button>
        </form>
      </template>
    </template>

    <template v-else-if="activeTab === 'decisions'">
      <div class="card decisions-toolbar"><span>{{ campaignHistory.length }} {{ t('campaignsLower') }}</span><select v-model="decisionStatusFilter"><option value="">{{ t('allStatuses') }}</option><option v-for="item in campaignStatuses" :key="item" :value="item">{{ enumLabel(item) }}</option></select></div>
      <div class="decision-history-grid">
        <article v-for="campaign in filteredCampaignHistory" :key="campaign.id" class="card history-card">
          <div class="campaign-card-top"><div><strong>{{ campaign.symbol }} · {{ campaign.setup }}</strong><div class="muted-copy">{{ campaign.trade_date || t('multiDay') }} · {{ campaign.context_name }} · {{ enumLabel(campaign.context_type) }}</div></div><span :class="['badge', statusClass(campaign.status)]">{{ enumLabel(campaign.status) }}</span></div>
          <div class="campaign-stats"><span><small>{{ t('direction') }}</small><strong>{{ enumLabel(campaign.direction) }}</strong></span><span><small>{{ t('horizon') }}</small><strong>{{ enumLabel(campaign.horizon) }}</strong></span><span><small>{{ t('result') }}</small><strong>{{ number(campaign.result_r) }}R</strong></span><span><small>{{ t('decision') }}</small><strong>{{ campaign.review?.decision_grade || '-' }}</strong></span></div>
          <details v-if="campaign.decision_snapshot"><summary>{{ t('originalSnapshot') }}</summary><div class="snapshot-detail"><p><b>{{ t('interpretation') }}:</b> {{ campaign.decision_snapshot.interpretation }}</p><p><b>{{ t('counterCase') }}:</b> {{ campaign.decision_snapshot.strongest_counter_case }}</p><p><b>{{ t('trigger') }}:</b> {{ campaign.decision_snapshot.entry_trigger }}</p><p><b>{{ t('invalidation') }}:</b> {{ campaign.decision_snapshot.invalidation }}</p></div></details>
        </article>
      </div>
    </template>

    <template v-else>
      <div v-if="!analytics" class="card">{{ t('loadingAnalytics') }}</div>
      <template v-else>
        <div class="journal-risk-strip analytics-summary"><div class="card risk-cell"><span>{{ t('sampleSize') }}</span><strong>{{ analytics.sample_size }}</strong></div><div class="card risk-cell"><span>{{ t('plannedAvgR') }}</span><strong>{{ number(analytics.plan_comparison.planned.average_r) }}R</strong></div><div class="card risk-cell"><span>{{ t('unplannedAvgR') }}</span><strong>{{ number(analytics.plan_comparison.unplanned.average_r) }}R</strong></div></div>
        <div class="analytics-grid">
          <div class="card"><div class="section-title">{{ t('setupEdge') }}</div><table class="trade-table"><thead><tr><th>{{ t('setup') }}</th><th>N</th><th>{{ t('avgR') }}</th><th>{{ t('totalR') }}</th></tr></thead><tbody><tr v-for="row in analytics.setup" :key="row.setup"><td>{{ row.setup }}</td><td>{{ row.campaigns }}</td><td>{{ number(row.average_r) }}</td><td>{{ number(row.total_r) }}</td></tr></tbody></table></div>
          <div class="card"><div class="section-title">{{ t('contextPerformance') }}</div><table class="trade-table"><thead><tr><th>{{ t('decisionContext') }}</th><th>N</th><th>{{ t('avgR') }}</th><th>{{ t('totalR') }}</th></tr></thead><tbody><tr v-for="row in analytics.context" :key="`${row.context__context_kind}-${row.context__context_type}`"><td>{{ enumLabel(row.context__context_kind) }} · {{ enumLabel(row.context__context_type) }}</td><td>{{ row.campaigns }}</td><td>{{ number(row.average_r) }}</td><td>{{ number(row.total_r) }}</td></tr></tbody></table></div>
          <div class="card"><div class="section-title">{{ t('attemptSequence') }}</div><table class="trade-table"><thead><tr><th>{{ t('attempt') }}</th><th>N</th><th>{{ t('avgR') }}</th><th>{{ t('totalR') }}</th></tr></thead><tbody><tr v-for="row in analytics.attempt_sequence" :key="row.sequence_no"><td>#{{ row.sequence_no }}</td><td>{{ row.attempts }}</td><td>{{ number(row.average_r) }}</td><td>{{ number(row.total_r) }}</td></tr></tbody></table></div>
        </div>
        <div v-if="analytics.sample_size < 20" class="card sample-warning">{{ t('sampleWarning') }}</div>
      </template>
    </template>

    <Teleport to="body">
      <div v-if="errorMessage" class="journal-toast" role="alert">
        <div><strong>{{ t('actionFailed') }}</strong><span>{{ errorMessage }}</span></div>
        <button class="secondary small-btn" @click="errorMessage = ''; groupingError = ''">{{ t('dismiss') }}</button>
      </div>
      <div v-if="decisionUpdateCampaign" class="journal-modal-backdrop" @click.self="decisionUpdateCampaign = null">
        <form class="journal-modal card decision-update-form" @submit.prevent="submitDecisionUpdate">
          <div class="builder-head"><div><strong>{{ t('decisionUpdate') }} · {{ decisionUpdateCampaign.symbol }}</strong><span>{{ t('decisionUpdateModalHelp') }}</span></div><button type="button" class="secondary small-btn" @click="decisionUpdateCampaign = null">{{ t('close') }}</button></div>
          <div class="journal-form-grid three-col">
            <label v-if="decisionUpdateCampaign.context_kind === 'swing'"><span>{{ t('positionStage') }}</span><select v-model="decisionUpdateForm.position_stage"><option v-for="item in positionStages" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label><span>{{ t('eventType') }}</span><select v-model="decisionUpdateForm.event_type"><option v-for="item in eventTypes" :key="item" :value="item">{{ enumLabel(item) }}</option></select></label>
            <label><span>{{ t('eventTime') }}</span><input v-model="decisionUpdateForm.event_at" type="datetime-local" required /></label>
          </div>
          <div class="journal-form-grid two-col">
            <label><span>{{ t('observedEvidence') }}</span><input v-model.trim="decisionUpdateForm.observed_evidence_text" required :placeholder="t('evidencePlaceholder')" /></label>
            <label><span>{{ t('interpretation') }}</span><input v-model.trim="decisionUpdateForm.interpretation" required /></label>
            <label><span>{{ t('updatedDecision') }}</span><input v-model.trim="decisionUpdateForm.decision" required :placeholder="t('updatedDecisionPlaceholder')" /></label>
            <label><span>{{ t('riskChange') }}</span><input v-model.trim="decisionUpdateForm.risk_change" :placeholder="t('riskChangePlaceholder')" /></label>
            <label><span>{{ t('invalidationUpdate') }}</span><input v-model.trim="decisionUpdateForm.invalidation_update" /></label>
            <label><span>{{ t('nextReview') }}</span><input v-model="decisionUpdateForm.next_review_at" type="datetime-local" /></label>
          </div>
          <div class="builder-actions"><button type="button" class="secondary" @click="decisionUpdateCampaign = null">{{ t('cancel') }}</button><button :disabled="saving">{{ t('saveDecisionUpdate') }}</button></div>
        </form>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  activateJournalCampaign, attachJournalFills, closeJournalCampaign, closeJournalContext,
  createCorrectionRecord, createDecisionUpdate, createDecisionVersion, createJournalCampaign, createJournalContext, createJournalToday,
  deleteJournalAttempt, deleteJournalCampaign, fetchJournalAnalytics, fetchJournalCampaigns, fetchJournalContexts, fetchJournalToday,
  importJournalFills, pauseJournalCampaign, resumeJournalCampaign, reviewJournalCampaign,
  startJournalContext, undoJournalGrouping, updateJournalCampaign,
} from '../api/journal'
import { responseRows } from '../api/pagination'
import { formatNumber } from '../utils/formatters'

const messages = {
  en: {
    language: 'Language', decisionLifecycle: 'Decision lifecycle', journalTitle: 'Journal', journalSubtitle: 'Save the judgment you had then, then make executions, outcomes, and reviews auditable evidence.',
    todayTab: 'Today', decisionsTab: 'Decisions', analyticsTab: 'Analytics', tradingDay: 'Trading day', actionFailed: 'Action failed', dismiss: 'Dismiss', loadingJournal: 'Loading journal…',
    startDay: 'Start the trading day', startDayHelp: 'Set the guardrails before creating sessions and trade decisions.', dailyRiskLimit: 'Daily risk limit', maximumCampaigns: 'Maximum decisions',
    marketEnvironment: 'Market environment', marketEnvironmentPlaceholder: 'Trend, range, volatile…', createTradingDay: 'Create trading day', dayStatus: 'Day status', netPnl: 'Net P&L', totalR: 'Total R',
    campaigns: 'Decisions', attempts: 'Attempts', riskBudget: 'Risk budget', notSet: 'Not set', sessions: 'Sessions', sessionsHelp: 'Divide the day into distinct decision environments.',
    decisionContexts: 'Decision contexts', decisionContextsHelp: 'Time segments for intraday trades; position stages for swing trades.', newContext: 'New context', createContext: 'Create context', noContexts: 'No decision contexts yet.',
    contextKind: 'Context kind', intradayContext: 'Intraday · time segment', swingContext: 'Swing · position stage', timeSegment: 'Time segment', positionStage: 'Position stage', decisionContext: 'Decision context',
    decisionUpdate: 'Decision update', eventType: 'Event type', eventTime: 'Event time', updatedDecision: 'Updated decision', updatedDecisionPlaceholder: 'Hold, add, reduce, exit…', riskChange: 'Risk change',
    riskChangePlaceholder: 'How does exposure or risk change?', invalidationUpdate: 'Invalidation update', nextReview: 'Next review', saveDecisionUpdate: 'Save decision update', multiDay: 'Multi-day', contextPerformance: 'Context performance',
    cancel: 'Cancel', newSession: 'New session', name: 'Name', openingSession: 'Opening session', type: 'Type', riskLimitR: 'Risk limit (R)', environment: 'Environment', volatileTrend: 'Volatile trend',
    allowedSetups: 'Allowed setups', setupExamples: 'Opening breakout, pullback', noTradeConditions: 'No-trade conditions', noTradePlaceholder: 'When should you stay out?', createSession: 'Create session',
    noSessions: 'No sessions yet.', environmentNotSet: 'Environment not set', campaignsLower: 'decisions', limit: 'Limit', start: 'Start', close: 'Close', newDecision: 'New decision',
    activeDecisions: 'Active decisions', decisionsHelp: 'One decision can contain multiple execution attempts.', createCampaign: 'Create decision', campaignSnapshot: 'Pre-trade decision snapshot',
    preTradeEditableHelp: 'Editable before the first fill. Every save creates a version; the latest version locks automatically on first execution.', editDecisionVersion: 'Edit pre-trade decision',
    versionSaveHelp: 'Saving creates a new version and preserves the prior record.', changeNote: 'What changed?', changeNotePlaceholder: 'Why did the plan change?', saveNewVersion: 'Save new version',
    editAndSaveVersion: 'Edit / save version', version: 'Version', versionHistory: 'Version history', initialVersion: 'Initial version', recordCorrection: 'Record correction', correction: 'Correction',
    correctionTarget: 'Correction target', lockedDecision: 'Locked decision', fieldName: 'Field name', correctionReason: 'Reason for correction', originalValue: 'Original value', correctedValue: 'Corrected value', saveCorrection: 'Save correction',
    snapshotImmutableHelp: 'Once saved, the snapshot is immutable and can only be reviewed afterward.', session: 'Session', symbol: 'Symbol', direction: 'Direction', horizon: 'Horizon', setup: 'Setup',
    openingBreakout: 'Opening breakout', riskAmount: 'Risk amount', maxRiskR: 'Max risk (R)', maximumAttempts: 'Maximum attempts', observedEvidence: 'Observed evidence',
    evidencePlaceholder: 'VWAP reclaim, higher low…', interpretation: 'Interpretation', interpretationPlaceholder: 'What do the facts imply?', strongestCounterCase: 'Strongest counter-case',
    counterCasePlaceholder: 'Why might this be wrong?', chosenAction: 'Chosen action', chosenActionPlaceholder: 'Enter, wait, reduce size…', entryTrigger: 'Entry trigger',
    entryTriggerPlaceholder: 'Specific observable trigger', invalidation: 'Invalidation', invalidationPlaceholder: 'What proves the thesis wrong?', timeStop: 'Time stop', timeStopPlaceholder: 'Exit if nothing happens by…',
    mutuallyExclusiveScenarios: 'Mutually exclusive scenarios', total: 'Total', scenario: 'Scenario', remove: 'Remove', probability: 'Probability', scenarioNamePlaceholder: 'Base, upside, failure…',
    confirmation: 'Confirmation', confirmationPlaceholder: 'Evidence that supports it', contradiction: 'Contradiction', contradictionPlaceholder: 'Evidence against it', plannedAction: 'Planned action',
    plannedActionPlaceholder: 'What will you do?', addThirdScenario: 'Add third scenario', savePlanned: 'Save as planned', saveAndActivate: 'Save & activate', createDecisionFirst: 'Create a decision snapshot before grouping executions.',
    readiness: 'Readiness', risk: 'Risk', result: 'Result', trigger: 'Trigger', activate: 'Activate', closeCampaign: 'Close decision', review: 'Review', fillsLower: 'fills',
    pauseCampaign: 'Pause', resumeCampaign: 'Resume', closePositionFirst: 'Open position · attach the closing fill first', deleteDirtyCampaign: 'Delete', deleteEmptyAttempt: 'Delete empty attempt',
    deleteCampaignConfirm: 'Delete this campaign and all of its pre-trade versions? This is only allowed when it has no fills.', deleteAttemptConfirm: 'Delete this empty attempt?',
    fillGrouping: 'Fill grouping workspace', fillGroupingHelp: 'Select fills to create an attempt, or move grouped fills to merge and split attempts.', selected: 'selected', csvImport: 'CSV import',
    groupingNextStep: 'After grouping:', groupingNextStepHelp: 'Entry fill → position opens → append updates while holding → attach the exit fill to the same attempt → position becomes closed → end the decision → review.',
    csvImportHelp: 'Import broker fills; duplicates are detected automatically.', targetCampaign: 'Target decision', selectCampaign: 'Select decision', targetAttempt: 'Target attempt', createNewAttempt: 'Create new attempt',
    attempt: 'Attempt', reentryReason: 'Re-entry reason', firstEntry: 'First entry', whatChanged: 'What changed?', reentryRequired: 'Required for a re-entry', applyGrouping: 'Apply grouping',
    undoGrouping: 'Undo last grouping', time: 'Time', side: 'Side', qty: 'Qty', price: 'Price', currentGroup: 'Current group', noFills: 'No fills for this day.', reviewQueue: 'Review queue', attemptsLower: 'attempts',
    campaignReview: 'Decision review', campaignReviewHelp: 'Grade the decision separately from execution and luck.', exitReason: 'Exit reason', actualScenario: 'Actual scenario', unclear: 'Unclear',
    decisionGrade: 'Decision grade', executionGrade: 'Execution grade', entryFollowed: 'Entry followed plan', managementFollowed: 'Management followed plan', exitFollowed: 'Exit followed plan',
    outcomeDrivers: 'Outcome drivers (max 2)', knowableThen: 'Knowable then', luckVariance: 'Luck / variance', processChange: 'Process change', counterCase: 'Counter-case', wouldRepeat: 'Would repeat?',
    oneLesson: 'One lesson', lessonPlaceholder: 'One concrete change for the next similar decision', submitReview: 'Submit review', allStatuses: 'All statuses', originalSnapshot: 'Original snapshot', decision: 'Decision grade',
    plannedAvgR: 'Planned avg R', unplannedAvgR: 'Unplanned avg R', setupEdge: 'Setup edge', attemptSequence: 'Attempt sequence', sessionPerformance: 'Session performance', sampleSize: 'Sample size', avgR: 'Avg R',
    loadingAnalytics: 'Loading analytics…', sampleWarning: 'Small sample: use these results as questions to investigate, not proof of an edge.', baseCase: 'Base case', failureCase: 'Failure case', alternativeCase: 'Alternative case',
    ungrouped: 'Ungrouped', chooseCsv: 'Choose CSV file', no: 'No', yes: 'Yes', decisionUpdateModalHelp: 'Append a new observation and action without rewriting the locked original decision.',
    groupingSucceeded: 'Grouping applied', netPosition: 'Net position', attemptStatus: 'Attempt status', groupingClosedNext: 'Net position is zero. You can end the decision and continue to review.', groupingOpenNext: 'This attempt still has an open position. The next closing fill will stay targeted to this attempt.',
    ungroupedFills: 'Ungrouped', groupedFills: 'Grouped', allFills: 'All fills', noUngroupedFills: 'No ungrouped fills. Switch to Grouped to review completed assignments.', groupingFailed: 'Grouping was not applied',
  },
  zh: {
    language: '语言', decisionLifecycle: '决策生命周期', journalTitle: '交易日志', journalSubtitle: '先保存当时的判断，再让成交、结果与复盘成为可审计的证据。',
    todayTab: '今日', decisionsTab: '决策记录', analyticsTab: '统计分析', tradingDay: '交易日', actionFailed: '操作失败', dismiss: '关闭提示', loadingJournal: '正在加载交易日志…',
    startDay: '开始交易日', startDayHelp: '先设置风险边界，再创建交易时段与交易决策。', dailyRiskLimit: '单日风险上限', maximumCampaigns: '最多决策数', marketEnvironment: '市场环境',
    marketEnvironmentPlaceholder: '趋势、震荡、高波动…', createTradingDay: '创建交易日', dayStatus: '当日状态', netPnl: '净盈亏', totalR: '总 R', campaigns: '决策数', attempts: '尝试次数', riskBudget: '风险预算', notSet: '未设置',
    sessions: '交易时段', sessionsHelp: '把一天划分为不同的决策环境。', decisionContexts: '决策上下文', decisionContextsHelp: '日内交易使用时间段，波段交易使用持仓阶段。', newContext: '新建上下文', createContext: '创建决策上下文', noContexts: '还没有决策上下文。',
    contextKind: '上下文类型', intradayContext: '日内 · 时间段', swingContext: '波段 · 持仓阶段', timeSegment: '时间段', positionStage: '持仓阶段', decisionContext: '决策上下文', decisionUpdate: '更新决策', eventType: '事件类型', eventTime: '事件时间',
    updatedDecision: '更新后的决策', updatedDecisionPlaceholder: '继续持有、加仓、减仓、退出…', riskChange: '风险变化', riskChangePlaceholder: '仓位或风险如何变化？', invalidationUpdate: '失效条件更新', nextReview: '下次复查', saveDecisionUpdate: '保存决策更新', multiDay: '跨日', contextPerformance: '决策上下文表现',
    cancel: '取消', newSession: '新建时段', name: '名称', openingSession: '开盘时段', type: '类型', riskLimitR: '风险上限（R）',
    environment: '环境', volatileTrend: '高波动趋势', allowedSetups: '允许的策略', setupExamples: '开盘突破、回调入场', noTradeConditions: '禁止交易条件', noTradePlaceholder: '什么情况下必须观望？',
    createSession: '创建时段', noSessions: '还没有交易时段。', environmentNotSet: '未设置市场环境', campaignsLower: '个决策', limit: '上限', start: '开始', close: '结束', newDecision: '新建决策',
    activeDecisions: '当前决策', decisionsHelp: '一个交易决策可以包含多次执行尝试。', createCampaign: '创建决策', campaignSnapshot: '交易前决策快照', snapshotImmutableHelp: '保存后快照不可修改，只能在交易后复盘。',
    preTradeEditableHelp: '首笔成交前可以编辑；每次保存都会产生新版本，首笔成交时自动锁定最新版本。', editDecisionVersion: '编辑交易前决策', versionSaveHelp: '保存会创建新版本，并保留此前的决策记录。',
    changeNote: '本次修改内容', changeNotePlaceholder: '为什么调整交易计划？', saveNewVersion: '保存新版本', editAndSaveVersion: '编辑 / 保存版本', version: '版本', versionHistory: '版本历史', initialVersion: '初始版本',
    recordCorrection: '记录修正', correction: '修正记录', correctionTarget: '修正对象', lockedDecision: '已锁定决策', fieldName: '字段名称', correctionReason: '修正原因', originalValue: '原始值', correctedValue: '修正值', saveCorrection: '保存修正记录',
    session: '交易时段', symbol: '标的', direction: '方向', horizon: '持仓周期', setup: '策略', openingBreakout: '开盘突破', riskAmount: '风险金额', maxRiskR: '最大风险（R）', maximumAttempts: '最多尝试次数',
    observedEvidence: '观察到的证据', evidencePlaceholder: '重新站上 VWAP、形成更高低点…', interpretation: '判断', interpretationPlaceholder: '这些事实意味着什么？', strongestCounterCase: '最强反方理由', counterCasePlaceholder: '这个判断为什么可能是错的？',
    chosenAction: '选择的行动', chosenActionPlaceholder: '入场、等待、减小仓位…', entryTrigger: '入场触发条件', entryTriggerPlaceholder: '明确、可观察的触发条件', invalidation: '失效条件', invalidationPlaceholder: '出现什么情况说明逻辑错误？',
    timeStop: '时间止损', timeStopPlaceholder: '到什么时间没有发展就退出？', mutuallyExclusiveScenarios: '互斥情景', total: '合计', scenario: '情景', remove: '删除', probability: '概率', scenarioNamePlaceholder: '基准、上涨、失败…',
    confirmation: '确认信号', confirmationPlaceholder: '什么证据支持该情景？', contradiction: '反证信号', contradictionPlaceholder: '什么证据否定该情景？', plannedAction: '计划行动', plannedActionPlaceholder: '你准备怎么做？',
    addThirdScenario: '添加第三种情景', savePlanned: '保存为计划', saveAndActivate: '保存并激活', createDecisionFirst: '请先创建决策快照，再归组成交。', readiness: '准备度', risk: '风险', result: '结果', trigger: '触发条件',
    activate: '激活', closeCampaign: '结束决策', review: '复盘', fillsLower: '笔成交', fillGrouping: '成交归组工作区', fillGroupingHelp: '选择成交后创建尝试；也可移动已归组的成交，以合并或拆分尝试。', selected: '项已选择',
    pauseCampaign: '暂停', resumeCampaign: '恢复', closePositionFirst: '持仓未平 · 请先把平仓成交归入当前尝试', deleteDirtyCampaign: '删除', deleteEmptyAttempt: '删除空尝试',
    deleteCampaignConfirm: '确定删除这个决策及其全部交易前版本吗？只有没有任何成交的决策可以删除。', deleteAttemptConfirm: '确定删除这个没有成交的空尝试吗？',
    csvImport: 'CSV 导入', csvImportHelp: '导入券商成交记录，系统会自动识别重复数据。', targetCampaign: '目标决策', selectCampaign: '选择决策', targetAttempt: '目标尝试', createNewAttempt: '创建新尝试', attempt: '尝试',
    groupingNextStep: '归组后的流程：', groupingNextStepHelp: '入场成交 → 形成持仓 → 持仓中追加决策更新 → 把平仓成交归入同一尝试 → 尝试自动变为已结束 → 结束决策 → 填写复盘。',
    reentryReason: '再次入场原因', firstEntry: '首次入场', whatChanged: '发生了什么变化？', reentryRequired: '再次入场时必填', applyGrouping: '执行归组', undoGrouping: '撤销上次归组', time: '时间', side: '买卖方向', qty: '数量', price: '价格',
    currentGroup: '当前归组', noFills: '当天没有成交记录。', reviewQueue: '待复盘', attemptsLower: '次尝试', campaignReview: '决策复盘', campaignReviewHelp: '把决策质量、执行质量与运气分别评分。', exitReason: '退出原因', actualScenario: '实际发生的情景',
    unclear: '不明确', decisionGrade: '决策评分', executionGrade: '执行评分', entryFollowed: '入场是否遵守计划', managementFollowed: '持仓管理是否遵守计划', exitFollowed: '退出是否遵守计划', outcomeDrivers: '结果驱动因素（最多 2 个）',
    knowableThen: '当时可知的信息', luckVariance: '运气 / 随机性', processChange: '流程改进', counterCase: '反方理由', wouldRepeat: '是否愿意重复该决策？', oneLesson: '一条经验', lessonPlaceholder: '下一次相似决策要做的一项具体改变', submitReview: '提交复盘',
    allStatuses: '全部状态', originalSnapshot: '原始决策快照', decision: '决策评分', plannedAvgR: '按计划交易平均 R', unplannedAvgR: '未按计划交易平均 R', setupEdge: '策略表现', attemptSequence: '尝试序列表现', sessionPerformance: '时段表现', sampleSize: '样本量', avgR: '平均 R',
    loadingAnalytics: '正在加载统计…', sampleWarning: '当前样本较少：请把结果当作需要验证的问题，而不是策略有效性的证明。', baseCase: '基准情景', failureCase: '失败情景', alternativeCase: '其他情景', ungrouped: '未归组', chooseCsv: '选择 CSV 文件', no: '否', yes: '是', decisionUpdateModalHelp: '只追加新的观察和行动，不改写已锁定的原始决策。',
    groupingSucceeded: '成交归组成功', netPosition: '净仓位', attemptStatus: '尝试状态', groupingClosedNext: '净仓位已经归零，可以结束决策并进入复盘。', groupingOpenNext: '该尝试仍有持仓；下一笔平仓成交会继续默认归入这个尝试。',
    ungroupedFills: '待归组', groupedFills: '已归组', allFills: '全部成交', noUngroupedFills: '没有待归组成交；可切换到“已归组”查看归组结果。', groupingFailed: '成交归组未完成',
  },
}

const enumMessages = {
  en: {
    draft: 'Draft', active: 'Active', planned: 'Planned', paused: 'Paused', closed: 'Closed', review_pending: 'Review pending', reviewed: 'Reviewed', cancelled: 'Cancelled', open: 'Open', scaling: 'Scaling', pending: 'Pending', voided: 'Voided',
    pre_trade: 'Pre-trade · editable', ready_to_close: 'Flat · ready to close', review: 'Review only',
    premarket: 'Pre-market', opening: 'Opening', morning: 'Morning', midday: 'Midday', power_hour: 'Power hour', custom: 'Custom', long: 'Long', short: 'Short', neutral: 'Neutral', scalp: 'Scalp', intraday: 'Intraday', swing: 'Swing', position: 'Position',
    idea_validation: 'Idea validation', initial_entry: 'Initial entry', position_building: 'Position building', holding: 'Holding', risk_reduction: 'Risk reduction', exit: 'Exit', price_action: 'Price action', economic_data: 'Economic data', news: 'News', earnings: 'Earnings', risk_event: 'Risk event', time_review: 'Scheduled review',
    planned_retry: 'Planned retry', new_signal: 'New signal', better_price: 'Better price', noise_stop: 'Noise stop', changed_setup: 'Changed setup', emotional: 'Emotional', target: 'Target', trailing_stop: 'Trailing stop', initial_stop: 'Initial stop',
    thesis_invalidated: 'Thesis invalidated', time_stop: 'Time stop', market_change: 'Market change', manual_risk: 'Manual risk exit', error: 'Error', yes: 'Yes', partly: 'Partly', no: 'No', BUY: 'Buy', SELL: 'Sell', buy: 'Buy', sell: 'Sell',
  },
  zh: {
    draft: '草稿', active: '进行中', planned: '已计划', paused: '已暂停', closed: '已结束', review_pending: '待复盘', reviewed: '已复盘', cancelled: '已取消', open: '持有中', scaling: '调整仓位中', pending: '待处理', voided: '已作废',
    pre_trade: '交易前 · 可编辑', ready_to_close: '已平仓 · 可结束', review: '结束 · 仅复盘',
    premarket: '盘前', opening: '开盘', morning: '上午', midday: '午间', power_hour: '尾盘时段', custom: '自定义', long: '做多', short: '做空', neutral: '中性', scalp: '超短线', intraday: '日内', swing: '波段', position: '中长线',
    idea_validation: '想法验证', initial_entry: '首次建仓', position_building: '逐步建仓', holding: '持有观察', risk_reduction: '降低风险', exit: '退出', price_action: '价格行为', economic_data: '经济数据', news: '新闻', earnings: '财报', risk_event: '风险事件', time_review: '定期复查',
    planned_retry: '计划内重试', new_signal: '出现新信号', better_price: '更优价格', noise_stop: '噪声止损', changed_setup: '策略条件改变', emotional: '情绪驱动', target: '达到目标', trailing_stop: '移动止损', initial_stop: '初始止损',
    thesis_invalidated: '交易逻辑失效', time_stop: '时间止损', market_change: '市场环境变化', manual_risk: '主动风险退出', error: '操作错误', yes: '是', partly: '部分遵守', no: '否', BUY: '买入', SELL: '卖出', buy: '买入', sell: '卖出',
  },
}

const storedLanguage = window.localStorage.getItem('journal-language')
const language = ref(storedLanguage === 'en' ? 'en' : 'zh')
function t(key) { return messages[language.value]?.[key] ?? messages.en[key] ?? key }
function setLanguage(next) {
  const oldBase = t('baseCase')
  const oldFailure = t('failureCase')
  const oldAlternative = t('alternativeCase')
  language.value = next
  window.localStorage.setItem('journal-language', next)
  for (const scenario of campaignForm?.scenarios || []) {
    if (scenario.name === oldBase) scenario.name = t('baseCase')
    else if (scenario.name === oldFailure) scenario.name = t('failureCase')
    else if (scenario.name === oldAlternative) scenario.name = t('alternativeCase')
  }
}
function enumLabel(value) {
  if (value == null || value === '') return '-'
  return enumMessages[language.value]?.[value] ?? String(value).replaceAll('_', ' ').replace(/\b\w/g, (m) => m.toUpperCase())
}

const tabs = [{ id: 'today', labelKey: 'todayTab' }, { id: 'decisions', labelKey: 'decisionsTab' }, { id: 'analytics', labelKey: 'analyticsTab' }]
const sessionTypes = ['premarket', 'opening', 'morning', 'midday', 'power_hour', 'custom']
const positionStages = ['idea_validation', 'initial_entry', 'position_building', 'holding', 'risk_reduction', 'exit']
const eventTypes = ['price_action', 'economic_data', 'news', 'earnings', 'risk_event', 'time_review', 'custom']
const reentryReasons = ['planned_retry', 'new_signal', 'better_price', 'noise_stop', 'changed_setup', 'emotional']
const exitReasons = ['target', 'trailing_stop', 'initial_stop', 'thesis_invalidated', 'time_stop', 'market_change', 'manual_risk', 'emotional', 'error']
const grades = ['A', 'B', 'C', 'D']
const planChoices = ['yes', 'partly', 'no']
const campaignStatuses = ['planned', 'active', 'paused', 'review_pending', 'reviewed', 'cancelled']

function localToday() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
function localDateTime() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 16)
}

const activeTab = ref('today')
const selectedDate = ref(localToday())
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const tradingDay = ref(null)
const swingContexts = ref([])
const ungroupedFills = ref([])
const campaignHistory = ref([])
const analytics = ref(null)
const selectedSessionId = ref('')
const showSessionForm = ref(false)
const showCampaignForm = ref(false)
const editingCampaignId = ref('')
const selectedFillIds = ref([])
const groupingCampaignId = ref('')
const groupingAttemptId = ref('')
const groupingResult = ref(null)
const groupingError = ref('')
const fillView = ref('ungrouped')
const reviewCampaign = ref(null)
const decisionUpdateCampaign = ref(null)
const correctionCampaign = ref(null)
const decisionStatusFilter = ref('')

const dayForm = reactive({ daily_risk_limit: null, max_trades: null, market_environment: '' })
const sessionForm = reactive({ name: '', context_kind: 'intraday', context_type: 'opening', risk_limit_r: 2, market_environment: '', allowed_setups_text: '', no_trade_conditions: '' })
const campaignForm = reactive({
  context: '', symbol: '', direction: 'long', horizon: 'intraday', setup: '', planned_risk_amount: 100,
  max_risk_r: 1, max_attempts: 2, observed_evidence_text: '', interpretation: '', strongest_counter_case: '',
  chosen_action: '', entry_trigger: '', invalidation: '', time_stop: '', change_note: '', scenarios: [blankScenario(t('baseCase'), 60), blankScenario(t('failureCase'), 40)],
})
const groupingForm = reactive({ reentry_reason: '', what_changed: '', was_planned: true })
const reviewForm = reactive({
  exit_reason: 'target', actual_scenario: '', entry_followed: 'yes', management_followed: 'yes', exit_followed: 'yes',
  decision_grade: 'B', execution_grade: 'B', outcome_drivers_text: '', hindsight_known_then: '', hindsight_luck: '',
  hindsight_process: '', would_repeat: true, lesson: '',
})
const decisionUpdateForm = reactive({
  position_stage: 'holding', event_type: 'price_action', event_at: localDateTime(), observed_evidence_text: '',
  interpretation: '', decision: '', risk_change: '', invalidation_update: '', next_review_at: '',
})
const correctionForm = reactive({ target_type: 'decision', field_name: '', original_value: '', corrected_value: '', reason: '' })

function blankScenario(name = '', probability = 0) { return { name, probability, confirmation: '', contradiction: '', planned_action: '' } }
const intradayContexts = computed(() => tradingDay.value?.contexts || [])
const contexts = computed(() => [...intradayContexts.value, ...swingContexts.value])
const todayCampaigns = computed(() => contexts.value.flatMap((item) => item.campaigns || []))
const reviewQueue = computed(() => todayCampaigns.value.filter((item) => ['review_pending', 'closed'].includes(item.status)))
const probabilityTotal = computed(() => campaignForm.scenarios.reduce((sum, item) => sum + Number(item.probability || 0), 0))
const probabilityValid = computed(() => probabilityTotal.value >= 99 && probabilityTotal.value <= 101)
const groupingCampaign = computed(() => todayCampaigns.value.find((item) => item.id === groupingCampaignId.value))
const groupingAttempts = computed(() => groupingCampaign.value?.attempts || [])
const selectedCampaignContext = computed(() => contexts.value.find((item) => item.id === campaignForm.context))
const availableHorizons = computed(() => selectedCampaignContext.value?.context_kind === 'swing' ? ['swing', 'position'] : ['scalp', 'intraday'])
const allDayFills = computed(() => {
  const rows = ungroupedFills.value.map((fill) => ({ ...fill, location: t('ungrouped'), grouped: false }))
  for (const campaign of todayCampaigns.value) {
    for (const attempt of campaign.attempts || []) {
      for (const fill of attempt.fills || []) rows.push({ ...fill, location: `${campaign.symbol} · ${t('attempt')} #${attempt.sequence_no}`, grouped: true })
    }
  }
  return rows.sort((a, b) => new Date(a.executed_at) - new Date(b.executed_at))
})
const displayedDayFills = computed(() => fillView.value === 'ungrouped' ? allDayFills.value.filter((item) => !item.grouped) : fillView.value === 'grouped' ? allDayFills.value.filter((item) => item.grouped) : allDayFills.value)
const filteredCampaignHistory = computed(() => decisionStatusFilter.value ? campaignHistory.value.filter((item) => item.status === decisionStatusFilter.value) : campaignHistory.value)

function number(value) { return formatNumber(value ?? 0) }
function money(value) {
  if (value == null || value === '') return '-'
  return new Intl.NumberFormat(language.value === 'zh' ? 'zh-CN' : 'en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value))
}
function shortTime(value) { return value ? new Date(value).toLocaleTimeString(language.value === 'zh' ? 'zh-CN' : 'en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-' }
function shortDateTime(value) { return value ? new Date(value).toLocaleString(language.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-' }
function numberClass(value) { return Number(value || 0) > 0 ? 'positive-value' : Number(value || 0) < 0 ? 'negative-value' : '' }
function statusClass(value) { return ['active', 'open'].includes(value) ? 'running' : ['reviewed', 'closed'].includes(value) ? 'success' : ['cancelled', 'voided'].includes(value) ? 'failed' : 'partial' }
function phaseClass(value) { return value === 'pre_trade' ? 'partial' : value === 'holding' ? 'running' : 'success' }
function readError(err) {
  const data = err?.response?.data
  if (typeof data === 'string') return data
  if (data?.detail) return data.detail
  if (data) return Object.entries(data).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`).join(' · ')
  return err?.message || 'Unknown error'
}
async function runAction(fn, onError = null) {
  saving.value = true; errorMessage.value = ''
  try { await fn(); return true } catch (err) {
    const message = readError(err)
    errorMessage.value = message
    if (onError) onError(message)
    return false
  } finally { saving.value = false }
}

async function loadToday() {
  loading.value = true; errorMessage.value = ''
  try {
    const res = await fetchJournalToday(selectedDate.value)
    tradingDay.value = res.data.trading_day
    ungroupedFills.value = res.data.ungrouped_fills || []
    const swingRes = await fetchJournalContexts({ context_kind: 'swing' })
    swingContexts.value = responseRows(swingRes.data).filter((item) => !['closed', 'reviewed'].includes(item.status))
    if (contexts.value.length && !contexts.value.some((item) => item.id === selectedSessionId.value)) selectedSessionId.value = contexts.value[0].id
    if (groupingCampaignId.value && !groupingAttemptId.value) syncGroupingAttemptTarget()
  } catch (err) { errorMessage.value = readError(err) } finally { loading.value = false }
}
async function loadHistory() { const res = await fetchJournalCampaigns(); campaignHistory.value = responseRows(res.data) }
async function loadAnalytics() { const res = await fetchJournalAnalytics(); analytics.value = res.data }
async function selectTab(tab) { activeTab.value = tab; if (tab === 'decisions') await runAction(loadHistory); if (tab === 'analytics') await runAction(loadAnalytics) }

async function createDay() { await runAction(async () => { await createJournalToday({ trade_date: selectedDate.value, ...dayForm }); await loadToday() }) }
async function createSession() {
  await runAction(async () => {
    await createJournalContext({
      trading_day: sessionForm.context_kind === 'intraday' ? tradingDay.value.id : null,
      name: sessionForm.name, context_kind: sessionForm.context_kind, context_type: sessionForm.context_type,
      risk_limit_r: sessionForm.risk_limit_r || null, market_environment: sessionForm.market_environment,
      allowed_setups: sessionForm.allowed_setups_text.split(',').map((v) => v.trim()).filter(Boolean),
      no_trade_conditions: sessionForm.no_trade_conditions,
    })
    Object.assign(sessionForm, { name: '', context_kind: 'intraday', context_type: 'opening', risk_limit_r: 2, market_environment: '', allowed_setups_text: '', no_trade_conditions: '' })
    showSessionForm.value = false; await loadToday()
  })
}
async function startSession(item) { await runAction(async () => { await startJournalContext(item.id); await loadToday() }) }
async function closeSession(item) { await runAction(async () => { await closeJournalContext(item.id); await loadToday() }) }
function openCampaignForm(contextId) {
  editingCampaignId.value = ''
  resetCampaignForm()
  campaignForm.context = contextId
  syncHorizonToContext()
  showCampaignForm.value = true
  window.scrollTo({ top: 350, behavior: 'smooth' })
}
function editCampaign(campaign) {
  const decision = campaign.current_decision
  if (!decision || !campaign.lifecycle?.can_edit_decision) return
  editingCampaignId.value = campaign.id
  Object.assign(campaignForm, {
    context: campaign.context, symbol: campaign.symbol, direction: campaign.direction, horizon: campaign.horizon,
    setup: campaign.setup, planned_risk_amount: Number(campaign.planned_risk_amount || 0), max_risk_r: Number(campaign.max_risk_r || 1),
    max_attempts: campaign.max_attempts, observed_evidence_text: (decision.observed_evidence || []).join(', '),
    interpretation: decision.interpretation, strongest_counter_case: decision.strongest_counter_case,
    chosen_action: decision.chosen_action, entry_trigger: decision.entry_trigger, invalidation: decision.invalidation,
    time_stop: decision.time_stop, change_note: '', scenarios: (decision.scenarios || []).map((item) => ({
      name: item.name, probability: Number(item.probability), confirmation: item.confirmation,
      contradiction: item.contradiction, planned_action: item.planned_action,
    })),
  })
  showCampaignForm.value = true
  window.scrollTo({ top: 350, behavior: 'smooth' })
}
function syncContextType() { sessionForm.context_type = sessionForm.context_kind === 'swing' ? 'idea_validation' : 'opening' }
function syncHorizonToContext() { campaignForm.horizon = selectedCampaignContext.value?.context_kind === 'swing' ? 'swing' : 'intraday' }
function addScenario() { if (campaignForm.scenarios.length < 3) campaignForm.scenarios.push(blankScenario(t('alternativeCase'), 0)) }
function removeScenario(index) { campaignForm.scenarios.splice(index, 1) }
function resetCampaignForm() {
  Object.assign(campaignForm, {
    context: selectedSessionId.value || contexts.value[0]?.id || '', symbol: '', direction: 'long', horizon: 'intraday', setup: '',
    planned_risk_amount: 100, max_risk_r: 1, max_attempts: 2, observed_evidence_text: '', interpretation: '',
    strongest_counter_case: '', chosen_action: '', entry_trigger: '', invalidation: '', time_stop: '',
    change_note: '',
    scenarios: [blankScenario(t('baseCase'), 60), blankScenario(t('failureCase'), 40)],
  })
}
async function createCampaign(activate) {
  await runAction(async () => {
    const campaignPayload = {
      context: campaignForm.context, symbol: campaignForm.symbol, direction: campaignForm.direction, setup: campaignForm.setup,
      horizon: campaignForm.horizon, max_risk_r: campaignForm.max_risk_r, planned_risk_amount: campaignForm.planned_risk_amount,
      max_attempts: campaignForm.max_attempts,
    }
    let campaign
    if (editingCampaignId.value) {
      const res = await updateJournalCampaign(editingCampaignId.value, campaignPayload)
      campaign = res.data
    } else {
      const res = await createJournalCampaign(campaignPayload)
      campaign = res.data
    }
    await createDecisionVersion(campaign.id, {
      observed_evidence: campaignForm.observed_evidence_text.split(',').map((v) => v.trim()).filter(Boolean),
      interpretation: campaignForm.interpretation, strongest_counter_case: campaignForm.strongest_counter_case,
      chosen_action: campaignForm.chosen_action, entry_trigger: campaignForm.entry_trigger,
      invalidation: campaignForm.invalidation, time_stop: campaignForm.time_stop, scenarios: campaignForm.scenarios,
      change_note: campaignForm.change_note,
    })
    if (activate && campaign.status === 'planned') await activateJournalCampaign(campaign.id)
    editingCampaignId.value = ''; showCampaignForm.value = false; resetCampaignForm(); await loadToday()
  })
}
async function activateCampaign(item) { await runAction(async () => { await activateJournalCampaign(item.id); await loadToday() }) }
async function pauseCampaign(item) { await runAction(async () => { await pauseJournalCampaign(item.id); await loadToday() }) }
async function resumeCampaign(item) { await runAction(async () => { await resumeJournalCampaign(item.id); await loadToday() }) }
async function closeCampaign(item) { await runAction(async () => { await closeJournalCampaign(item.id); await loadToday() }) }
async function removeCampaign(item) {
  if (!window.confirm(t('deleteCampaignConfirm'))) return
  await runAction(async () => { await deleteJournalCampaign(item.id); await loadToday() })
}
async function removeAttempt(item) {
  if (!window.confirm(t('deleteAttemptConfirm'))) return
  await runAction(async () => { await deleteJournalAttempt(item.id); await loadToday() })
}
async function groupSelectedFills() {
  groupingError.value = ''
  await runAction(async () => {
    const selectedIds = [...selectedFillIds.value]
    const res = await attachJournalFills(groupingCampaignId.value, {
      fill_ids: selectedFillIds.value, attempt_id: groupingAttemptId.value || null,
      reentry_reason: groupingForm.reentry_reason, what_changed: groupingForm.what_changed,
      was_planned: groupingForm.was_planned,
    })
    const affectedAttempt = (res.data.attempts || []).find((attempt) => attempt.fills.some((fill) => selectedIds.includes(fill.id)))
    groupingResult.value = affectedAttempt ? {
      campaignId: res.data.id, symbol: res.data.symbol, setup: res.data.setup,
      attemptId: affectedAttempt.id, sequenceNo: affectedAttempt.sequence_no, status: affectedAttempt.status,
      fillCount: affectedAttempt.fills.length, netQuantity: affectedAttempt.net_quantity,
    } : null
    selectedFillIds.value = []
    groupingAttemptId.value = affectedAttempt && ['open', 'scaling'].includes(affectedAttempt.status) ? affectedAttempt.id : ''
    groupingForm.reentry_reason = ''; groupingForm.what_changed = ''
    fillView.value = 'ungrouped'
    await loadToday()
  }, (message) => { groupingError.value = message })
}
function syncGroupingAttemptTarget() {
  const openAttempts = groupingAttempts.value.filter((item) => ['open', 'scaling'].includes(item.status))
  groupingAttemptId.value = openAttempts.length === 1 ? openAttempts[0].id : ''
}
async function importCsv(event) {
  const file = event.target.files?.[0]
  if (!file) return
  await runAction(async () => { await importJournalFills(file); await loadToday() })
  event.target.value = ''
}
async function undoGrouping() {
  await runAction(async () => { await undoJournalGrouping(groupingCampaignId.value); await loadToday() })
}
function openReview(campaign) { reviewCampaign.value = campaign; reviewForm.actual_scenario = campaign.decision_snapshot?.scenarios?.[0]?.id || ''; setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }), 0) }
function openDecisionUpdate(campaign) {
  decisionUpdateCampaign.value = campaign
  Object.assign(decisionUpdateForm, {
    position_stage: campaign.context_type || 'holding', event_type: 'price_action', event_at: localDateTime(),
    observed_evidence_text: '', interpretation: '', decision: '', risk_change: '', invalidation_update: '', next_review_at: '',
  })
}
async function submitDecisionUpdate() {
  await runAction(async () => {
    await createDecisionUpdate(decisionUpdateCampaign.value.id, {
      position_stage: decisionUpdateCampaign.value.context_kind === 'swing' ? decisionUpdateForm.position_stage : null,
      event_type: decisionUpdateForm.event_type,
      event_at: new Date(decisionUpdateForm.event_at).toISOString(),
      observed_evidence: decisionUpdateForm.observed_evidence_text.split(',').map((value) => value.trim()).filter(Boolean),
      interpretation: decisionUpdateForm.interpretation,
      decision: decisionUpdateForm.decision,
      risk_change: decisionUpdateForm.risk_change,
      invalidation_update: decisionUpdateForm.invalidation_update,
      next_review_at: decisionUpdateForm.next_review_at ? new Date(decisionUpdateForm.next_review_at).toISOString() : null,
    })
    decisionUpdateCampaign.value = null
    await loadToday()
  })
}
function openCorrection(campaign) {
  correctionCampaign.value = campaign
  Object.assign(correctionForm, { target_type: 'decision', field_name: '', original_value: '', corrected_value: '', reason: '' })
}
function parseCorrectionValue(value) {
  const trimmed = String(value ?? '').trim()
  if (!trimmed) return ''
  try { return JSON.parse(trimmed) } catch { return trimmed }
}
async function submitCorrection() {
  await runAction(async () => {
    await createCorrectionRecord(correctionCampaign.value.id, {
      target_type: correctionForm.target_type,
      field_name: correctionForm.field_name,
      original_value: parseCorrectionValue(correctionForm.original_value),
      corrected_value: parseCorrectionValue(correctionForm.corrected_value),
      reason: correctionForm.reason,
    })
    correctionCampaign.value = null
    await loadToday()
  })
}
async function submitReview() {
  await runAction(async () => {
    await reviewJournalCampaign(reviewCampaign.value.id, {
      exit_reason: reviewForm.exit_reason, actual_scenario: reviewForm.actual_scenario || null,
      entry_followed: reviewForm.entry_followed, management_followed: reviewForm.management_followed,
      exit_followed: reviewForm.exit_followed, decision_grade: reviewForm.decision_grade,
      execution_grade: reviewForm.execution_grade,
      outcome_drivers: reviewForm.outcome_drivers_text.split(',').map((v) => v.trim()).filter(Boolean).slice(0, 2),
      hindsight_known_then: reviewForm.hindsight_known_then, hindsight_luck: reviewForm.hindsight_luck,
      hindsight_process: reviewForm.hindsight_process, would_repeat: reviewForm.would_repeat, lesson: reviewForm.lesson,
    })
    reviewCampaign.value = null; await loadToday()
  })
}

onMounted(loadToday)
</script>

<style scoped>
.decision-journal { display: grid; gap: 16px; }
.journal-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.journal-hero-tools { display: flex; align-items: flex-end; gap: 12px; }
.language-switch { display: flex; gap: 3px; padding: 3px; border: 1px solid var(--line); border-radius: 10px; background: #f1f5fb; }
.language-switch button { min-height: 34px; padding: 6px 11px; border: 0; border-radius: 7px; background: transparent; color: var(--tv-muted); font-size: 12px; font-weight: 750; }
.language-switch button.active { background: #2563eb; color: #fff; box-shadow: 0 2px 7px rgba(37, 99, 235, .22); }
.journal-date-control { display: grid; gap: 6px; min-width: 180px; color: var(--tv-muted); font-size: 12px; font-weight: 700; }
.journal-tabs { display: flex; gap: 8px; padding: 8px; width: fit-content; }
.journal-error { display: flex; align-items: center; gap: 12px; color: var(--negative); border-color: #fecaca; }
.journal-error span { flex: 1; }
.journal-toast { position: fixed; right: 24px; bottom: 24px; z-index: 2200; display: flex; align-items: center; gap: 16px; width: min(520px, calc(100vw - 48px)); padding: 14px 16px; border: 1px solid #fca5a5; border-radius: 12px; background: #fff; color: var(--negative); box-shadow: 0 18px 50px rgba(127, 29, 29, .22); }
.journal-toast > div { display: grid; gap: 3px; flex: 1; }
.journal-toast span { color: #7f1d1d; font-size: 12px; }
.journal-empty-state { display: grid; gap: 18px; }
.journal-risk-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.risk-cell { display: grid; gap: 7px; padding: 14px 16px; }
.risk-cell span { color: var(--tv-muted); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .05em; }
.risk-cell strong { font-size: 18px; }
.positive-value { color: var(--positive); }
.negative-value { color: var(--negative); }
.journal-workspace-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-items: start; }
.journal-column, .journal-main-column { display: grid; gap: 12px; }
.context-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.column-heading, .card-title-row, .campaign-card-top, .builder-head, .scenario-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.column-heading .section-title { margin-bottom: 2px; }
.inline-journal-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.inline-journal-form label, .campaign-builder label, .review-form label, .grouping-controls label { display: grid; gap: 5px; }
label span { color: var(--tv-muted); font-size: 11px; font-weight: 750; }
.wide { grid-column: 1 / -1; }
.session-card { cursor: pointer; display: grid; gap: 12px; transition: border-color .15s, transform .15s; }
.session-card:hover, .session-card.selected { border-color: #93b4ff; transform: translateY(-1px); }
.session-metrics, .row-actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.session-metrics span { padding: 5px 8px; border-radius: 999px; background: #f1f5fb; color: var(--tv-muted); font-size: 11px; font-weight: 700; }
.campaign-builder { display: grid; gap: 16px; border-color: #a9c2ff; box-shadow: 0 16px 38px rgba(37,99,235,.09); }
.builder-head > div { display: grid; gap: 3px; }
.builder-head strong { font-size: 17px; }
.builder-head span { color: var(--tv-muted); font-size: 12px; }
.journal-form-grid { display: grid; gap: 10px; }
.journal-form-grid.two-col { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.journal-form-grid.three-col { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.journal-form-grid.four-col { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.scenario-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.scenario-card { display: grid; gap: 8px; padding: 12px; border: 1px solid #dfe7f3; border-radius: 12px; background: #f9fbff; }
.scenario-card-head { display: flex; justify-content: space-between; align-items: center; }
.text-button { border: 0; padding: 0; background: transparent; color: var(--negative); font-size: 11px; }
.probability-total { color: var(--negative); font-weight: 800; }
.probability-total.valid { color: var(--positive); }
.builder-actions { display: flex; justify-content: flex-end; gap: 10px; }
.campaign-card { display: grid; gap: 12px; }
.campaign-card-top strong { font-size: 16px; }
.campaign-badges { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
.campaign-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.campaign-stats span { display: grid; gap: 3px; padding: 9px 10px; background: #f7f9fd; border-radius: 10px; }
.campaign-stats small { color: var(--tv-muted); font-size: 10px; text-transform: uppercase; font-weight: 750; }
.campaign-stats strong { font-size: 13px; }
.snapshot-summary { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 10px; background: #f4f7fc; border-radius: 11px; }
.snapshot-summary > div:not(.scenario-chips) { display: grid; gap: 3px; }
.snapshot-summary span { color: var(--tv-muted); font-size: 10px; }
.snapshot-summary strong { font-size: 12px; font-weight: 650; }
.scenario-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.scenario-chips span { padding: 4px 7px; border-radius: 999px; background: #e6eeff; color: #2454b8; font-weight: 750; }
.snapshot-summary code { justify-self: end; color: var(--tv-muted); font-size: 10px; }
.attempt-list { display: grid; border-top: 1px solid var(--line); }
.attempt-row { display: grid; grid-template-columns: 40px repeat(4, 1fr) auto; gap: 10px; align-items: center; padding: 8px 0; border-bottom: 1px solid #edf1f7; font-size: 12px; }
.decision-update-list { display: grid; gap: 6px; padding-top: 10px; border-top: 1px solid var(--line); }
.decision-update-row { display: grid; grid-template-columns: 120px 120px minmax(0, 1fr); gap: 10px; align-items: center; padding: 8px 10px; border-radius: 9px; background: #f7f9fd; font-size: 12px; }
.decision-update-row > span:first-child { color: var(--tv-muted); }
.decision-update-form { display: grid; gap: 12px; padding: 13px; border: 1px solid #b8c8e8; border-radius: 11px; background: #f8faff; }
.decision-update-form label { display: grid; gap: 5px; }
.journal-modal-backdrop { position: fixed; inset: 0; z-index: 2000; display: grid; place-items: center; padding: 24px; background: rgba(15, 23, 42, .55); backdrop-filter: blur(2px); }
.journal-modal { width: min(900px, 100%); max-height: calc(100vh - 48px); overflow: auto; padding: 20px; box-shadow: 0 24px 70px rgba(15, 23, 42, .28); }
.version-history { padding: 9px 11px; border: 1px solid var(--line); border-radius: 10px; background: #fbfcfe; }
.version-history summary { cursor: pointer; color: #2454b8; font-size: 12px; font-weight: 750; }
.version-row { display: grid; grid-template-columns: 42px 135px minmax(0, 1fr); gap: 8px; padding: 7px 0; border-bottom: 1px solid #edf1f7; font-size: 11px; }
.version-row:last-child { border-bottom: 0; }
.version-row span { color: var(--tv-muted); }
.correction-button { color: #8a5b05; }
.delete-button { color: var(--negative); }
.flow-hint { padding: 5px 8px; border-radius: 8px; background: #fff8e7; color: #8a5b05; font-size: 11px; font-weight: 750; }
.correction-list { display: grid; gap: 6px; }
.correction-row { display: grid; grid-template-columns: 180px minmax(0, 1fr) 120px; gap: 10px; padding: 8px 10px; border-radius: 9px; background: #fff8e7; color: #7c4a03; font-size: 11px; }
.correction-row small { color: #9a6b18; text-align: right; }
.correction-form { border-color: #f3d39b; background: #fffaf0; }
.grouping-workspace { display: grid; gap: 14px; }
.grouping-flow-guide { display: flex; gap: 7px; align-items: baseline; padding: 10px 12px; border-radius: 10px; background: #eef4ff; color: #2454b8; font-size: 12px; }
.grouping-flow-guide span { color: #48658f; }
.grouping-error { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid #fca5a5; border-radius: 11px; background: #fff1f2; color: #b91c1c; }
.grouping-error span { flex: 1; font-size: 12px; }
.grouping-result { display: grid; grid-template-columns: 1.2fr 1fr minmax(220px, 1.5fr) auto; gap: 14px; align-items: center; padding: 12px 14px; border: 1px solid #b8c8e8; border-radius: 11px; background: #f4f8ff; }
.grouping-result.complete { border-color: #a7d8bd; background: #f0faf4; }
.grouping-result > div:first-child { display: grid; gap: 3px; }
.grouping-result > div:first-child span, .grouping-result p { margin: 0; color: var(--tv-muted); font-size: 11px; }
.grouping-result-metrics { display: flex; gap: 14px; flex-wrap: wrap; }
.grouping-result-metrics span { display: grid; gap: 2px; color: var(--tv-muted); font-size: 10px; }
.grouping-result-metrics strong { color: var(--tv-text); font-size: 13px; }
.fill-view-tabs { display: flex; gap: 6px; }
.fill-view-tabs button.active { border-color: #2563eb; background: #e9f0ff; color: #2454b8; }
.csv-import-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 10px 12px; border: 1px dashed #b8c8e8; border-radius: 11px; background: #f8faff; }
.csv-import-row > div { display: grid; gap: 3px; }
.csv-import-row span { color: var(--tv-muted); font-size: 11px; }
.csv-file-picker { cursor: pointer; }
.csv-file-picker > span { display: inline-flex; align-items: center; min-height: 36px; padding: 7px 12px; border: 1px solid #b8c8e8; border-radius: 8px; background: #fff; color: #2454b8; font-size: 12px; font-weight: 750; }
.csv-file-picker input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.grouping-controls { display: grid; grid-template-columns: 1.1fr 1fr 1fr 1.4fr auto auto; gap: 10px; align-items: end; }
.compact-fill-table input[type="checkbox"] { width: auto; }
.review-queue { display: grid; gap: 12px; }
.review-queue-grid { display: flex; gap: 9px; flex-wrap: wrap; }
.review-queue-item { display: grid; gap: 3px; text-align: left; background: #fff7e8; color: #7c4a03; border: 1px solid #f3d39b; }
.review-queue-item span { font-size: 11px; }
.review-form { display: grid; gap: 16px; border-color: #f3d39b; }
.review-result-strip { display: flex; gap: 24px; padding: 11px 13px; border-radius: 10px; background: #f7f9fd; }
.decisions-toolbar { display: flex; justify-content: space-between; align-items: center; }
.decisions-toolbar select { max-width: 220px; }
.decision-history-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.history-card { display: grid; gap: 13px; }
.history-card summary { cursor: pointer; color: #2454b8; font-weight: 750; }
.snapshot-detail { margin-top: 10px; padding: 10px 12px; border-radius: 10px; background: #f7f9fd; font-size: 12px; }
.snapshot-detail p { margin: 5px 0; }
.analytics-summary { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.analytics-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.sample-warning { color: #8a5b05; background: #fff8e7; border-color: #f3d39b; }
.empty-row { color: var(--tv-muted); text-align: center; }
@media (max-width: 1180px) {
  .journal-risk-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .journal-workspace-grid { grid-template-columns: 1fr; }
  .grouping-controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grouping-result { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .analytics-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .journal-hero { align-items: stretch; flex-direction: column; }
  .journal-hero-tools { align-items: stretch; flex-direction: column; }
  .language-switch { width: fit-content; }
  .journal-risk-strip, .analytics-summary, .journal-form-grid.two-col, .journal-form-grid.three-col, .journal-form-grid.four-col, .scenario-grid, .decision-history-grid { grid-template-columns: 1fr; }
  .campaign-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grouping-controls { grid-template-columns: 1fr; }
  .grouping-result { grid-template-columns: 1fr; }
  .journal-modal-backdrop { padding: 12px; }
  .journal-modal { max-height: calc(100vh - 24px); padding: 14px; }
  .journal-toast { right: 12px; bottom: 12px; width: calc(100vw - 24px); }
  .grouping-error { align-items: flex-start; flex-direction: column; }
  .snapshot-summary { grid-template-columns: 1fr; }
  .decision-update-row, .version-row, .correction-row, .attempt-row { grid-template-columns: 1fr; }
  .correction-row small { text-align: left; }
  .grouping-flow-guide { align-items: flex-start; flex-direction: column; }
}
</style>
