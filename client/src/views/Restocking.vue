<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="!initialized && loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="!initialized && error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card controls-card">
        <div class="budget-row">
          <label class="budget-label" for="restock-budget">{{ t('restocking.budget') }}</label>
          <div class="budget-value">{{ money(budget) }}</div>
        </div>
        <input
          id="restock-budget"
          v-model.number="budget"
          class="budget-slider"
          type="range"
          min="0"
          :max="sliderMax"
          :step="sliderStep"
          :aria-label="t('restocking.budget')"
          :disabled="sliderMax === 0"
        />
        <div class="slider-scale">
          <span>{{ money(0) }}</span>
          <span>{{ money(sliderMax) }}</span>
        </div>

        <div class="strategy-row">
          <span class="strategy-label" id="restock-strategy-label">{{ t('restocking.strategy') }}</span>
          <div class="segmented" role="group" aria-labelledby="restock-strategy-label">
            <button
              v-for="option in strategyOptions"
              :key="option.value"
              type="button"
              :class="['segment', { active: strategy === option.value }]"
              :aria-pressed="strategy === option.value"
              @click="strategy = option.value"
            >
              {{ t(option.label) }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="successMessage" class="success-message" role="status">{{ successMessage }}</div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.selectedTotal') }}</div>
          <div class="stat-value">{{ money(selectedTotal) }}</div>
        </div>
        <div :class="['stat-card', budgetRemaining >= 0 ? 'success' : 'danger']">
          <div class="stat-label">{{ t('restocking.budgetRemaining') }}</div>
          <div class="stat-value">{{ money(budgetRemaining) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.recommended') }}</div>
          <div class="stat-value stat-value-small">
            {{ t('restocking.itemsSelected', { count: selectedItems.length, total: recommended.length }) }}
          </div>
        </div>
      </div>

      <div :class="['card', { refreshing: loading }]">
        <div class="card-header header-with-action">
          <h3 class="card-title">{{ t('restocking.recommended') }} ({{ recommended.length }})</h3>
          <button
            type="button"
            class="place-order-btn"
            :disabled="selectedItems.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="maxBudget === 0" class="empty-state">{{ t('restocking.nothingToRestock') }}</div>
        <div v-else-if="recommended.length === 0" class="empty-state">{{ t('restocking.nothingAffordable') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th class="col-select">{{ t('restocking.table.select') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.onOrder') }}</th>
                <th class="num">{{ t('restocking.table.forecast') }}</th>
                <th class="num">{{ t('restocking.table.shortfall') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.cost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommended" :key="item.sku">
                <td class="col-select">
                  <input
                    v-model="selection[item.sku]"
                    type="checkbox"
                    :aria-label="`${t('restocking.table.select')}: ${item.name}`"
                  />
                </td>
                <td>
                  <strong>{{ item.name }}</strong>
                  <div class="sku">{{ item.sku }}</div>
                </td>
                <td>{{ item.category }}</td>
                <td>{{ item.supplier_name }}</td>
                <td class="num">{{ item.quantity_on_hand }}</td>
                <td class="num">{{ item.quantity_on_order }}</td>
                <td class="num">
                  {{ item.forecasted_demand }}
                  <span v-if="trendClass(item.trend)" :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num"><strong>{{ item.shortfall }}</strong></td>
                <td class="num">{{ money(item.unit_cost) }}</td>
                <td class="num"><strong>{{ money(item.total_cost) }}</strong></td>
                <td><span class="badge info">{{ t('orders.submitted.leadTimeDays', { days: item.lead_time_days }) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="skipped.length > 0" :class="['card', 'muted-card', { refreshing: loading }]">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.notAffordable') }} ({{ skipped.length }})</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th class="num">{{ t('restocking.table.shortfall') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.cost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in skipped" :key="item.sku">
                <td>
                  {{ item.name }}
                  <div class="sku">{{ item.sku }}</div>
                </td>
                <td>{{ item.category }}</td>
                <td>{{ item.supplier_name }}</td>
                <td class="num">{{ item.shortfall }}</td>
                <td class="num">{{ money(item.unit_cost) }}</td>
                <td class="num">{{ money(item.total_cost) }}</td>
                <td>{{ t('orders.submitted.leadTimeDays', { days: item.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()

    const initialized = ref(false)
    const loading = ref(true)
    const submitting = ref(false)
    const error = ref(null)
    const successMessage = ref('')

    const maxBudget = ref(0)
    const budget = ref(0)
    const strategy = ref('urgency')
    const recommended = ref([])
    const skipped = ref([])
    // sku -> boolean; reset to all-checked whenever a fresh recommendation arrives
    const selection = ref({})

    const strategyOptions = [
      { value: 'urgency', label: 'restocking.strategyUrgency' },
      { value: 'value', label: 'restocking.strategyValue' }
    ]

    // Slider max is rounded up so the full-coverage budget is always reachable.
    const sliderMax = computed(() => Math.ceil(maxBudget.value))
    const sliderStep = computed(() => Math.max(1, Math.round(sliderMax.value / 100)))

    const selectedItems = computed(() => recommended.value.filter(i => selection.value[i.sku]))
    const selectedTotal = computed(() => selectedItems.value.reduce((sum, i) => sum + i.total_cost, 0))
    const budgetRemaining = computed(() => budget.value - selectedTotal.value)

    const money = (amount) => formatCurrency(amount, currentCurrency.value)
    const trendClass = (trend) => ['increasing', 'decreasing', 'stable'].includes(trend)

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString
      return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    // Each request gets an increasing id; only the latest request may write state.
    // Without this, a slow response for an older slider position could overwrite a newer one.
    let requestId = 0

    const applyResult = (data) => {
      recommended.value = data.recommended
      skipped.value = data.skipped
      maxBudget.value = data.max_budget
      const next = {}
      data.recommended.forEach(i => { next[i.sku] = true })
      selection.value = next
    }

    const loadRecommendations = async () => {
      const id = ++requestId
      loading.value = true
      try {
        const data = await api.getRestockRecommendations(budget.value, strategy.value)
        if (id !== requestId) return // stale response
        applyResult(data)
        error.value = null
        // Shortfalls shrink after an order is placed; keep the budget inside the new slider range.
        if (budget.value > Math.ceil(data.max_budget)) {
          budget.value = Math.ceil(data.max_budget)
        }
      } catch (err) {
        if (id !== requestId) return
        error.value = t('restocking.loadFailed')
        console.error('Restocking load error:', err)
      } finally {
        if (id === requestId) {
          loading.value = false
          initialized.value = true
        }
      }
    }

    let debounceTimer = null
    const cancelDebounce = () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
        debounceTimer = null
      }
    }
    const scheduleLoad = () => {
      cancelDebounce()
      debounceTimer = setTimeout(() => {
        debounceTimer = null
        loadRecommendations()
      }, DEBOUNCE_MS)
    }

    // Ignored until the first load finishes, so setting the default budget in init()
    // does not queue a duplicate fetch.
    watch([budget, strategy], () => {
      if (initialized.value) scheduleLoad()
    })

    const init = async () => {
      try {
        // budget=0 returns max_budget (cost to cover every shortfall) without needing
        // any items to fit, so we can size the slider before the user touches it.
        const data = await api.getRestockRecommendations(0, strategy.value)
        maxBudget.value = data.max_budget
        const max = Math.ceil(data.max_budget)
        const step = Math.max(1, Math.round(max / 100))
        const half = Math.round(max / 2 / step) * step
        if (half > 0) {
          budget.value = half
          await loadRecommendations()
        } else {
          applyResult(data)
          loading.value = false
          initialized.value = true
        }
      } catch (err) {
        error.value = t('restocking.loadFailed')
        console.error('Restocking init error:', err)
        loading.value = false
      }
    }

    const placeOrder = async () => {
      if (selectedItems.value.length === 0 || submitting.value) return
      submitting.value = true
      error.value = null
      successMessage.value = ''
      try {
        // Quantity is always the full shortfall: the server only recommends whole-shortfall
        // lines (an item is either fully covered or skipped), so partial quantities never occur.
        const order = await api.placeRestockOrder(
          selectedItems.value.map(i => ({ sku: i.sku, quantity: i.shortfall }))
        )
        successMessage.value = t('restocking.orderPlaced', {
          orderNumber: order.order_number,
          date: formatDate(order.expected_delivery),
          days: order.lead_time_days
        })
        // Placed items now count as incoming on the server, so they drop out of the list.
        cancelDebounce()
        await loadRecommendations()
      } catch (err) {
        error.value = (err.response && err.response.data && err.response.data.detail) || t('restocking.orderFailed')
        console.error('Place order error:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(init)
    onBeforeUnmount(() => {
      cancelDebounce()
      requestId++ // ignore any in-flight response after leaving the page
    })

    return {
      t,
      initialized,
      loading,
      submitting,
      error,
      successMessage,
      maxBudget,
      budget,
      strategy,
      strategyOptions,
      sliderMax,
      sliderStep,
      recommended,
      skipped,
      selection,
      selectedItems,
      selectedTotal,
      budgetRemaining,
      money,
      trendClass,
      placeOrder
    }
  }
}
</script>

<style scoped>
.controls-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.budget-label,
.strategy-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-slider:disabled {
  cursor: not-allowed;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.strategy-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid #f1f5f9;
}

.segmented {
  display: inline-flex;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.segment {
  padding: 0.5rem 1rem;
  border: none;
  background: white;
  color: #64748b;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.segment + .segment {
  border-left: 1px solid #e2e8f0;
}

.segment:hover {
  background: #f8fafc;
  color: #0f172a;
}

.segment.active {
  background: #eff6ff;
  color: #2563eb;
}

.segment:focus-visible,
.place-order-btn:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.success-message {
  background: #d1fae5;
  border: 1px solid #10b981;
  color: #065f46;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
  font-size: 0.875rem;
}

.stat-value-small {
  font-size: 1.125rem;
}

.header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.place-order-btn {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 8px;
  background: #2563eb;
  color: white;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

/* Dim (rather than hide) tables during refetch so the slider does not jump */
.refreshing {
  opacity: 0.6;
  transition: opacity 0.2s;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.col-select {
  width: 64px;
  text-align: center;
}

.num {
  text-align: right;
  white-space: nowrap;
}

.sku {
  font-size: 0.75rem;
  color: #64748b;
}

.muted-card {
  color: #64748b;
}

.muted-card td {
  color: #64748b;
}

@media (max-width: 640px) {
  .budget-value {
    font-size: 1.5rem;
  }
}
</style>
