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
      </nav>
      <div class="online-pill"><i /> SYSTEM ONLINE</div>
    </header>
    <RouterView />
  </main>
</template>
