<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import ParticleField from './components/ParticleField.vue'
</script>

<template>
  <main class="app-shell">
    <ParticleField />
    <div class="ambient ambient-one" />
    <div class="ambient ambient-two" />
    <header class="topbar glass-panel">
      <RouterLink class="logo" to="/"><span>A</span><b>Agent Platform</b></RouterLink>
      <nav>
        <RouterLink to="/">控制中心</RouterLink>
        <RouterLink to="/agents/listing-creation">Listing 创作</RouterLink>
        <RouterLink to="/agents/listing-optimization">Listing 优化</RouterLink>
        <RouterLink to="/agents/product-research">Amazon 选品</RouterLink>
      </nav>
      <div class="online-pill"><i /> SYSTEM ONLINE</div>
    </header>
    <RouterView />
  </main>
</template>

<style>
.agent-grid { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.research-layout { grid-template-columns: 48px minmax(0, 1fr) 340px; }
.research-layout.history-open { grid-template-columns: 280px minmax(0, 1fr) 340px; }
@media (max-width: 900px) {
  .research-layout, .research-layout.history-open { grid-template-columns: 1fr; }
}
</style>
