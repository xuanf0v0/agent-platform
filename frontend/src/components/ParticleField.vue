<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
}

const PARTICLE_COUNT = 115
const MIN_DISTANCE = 30
const LINK_DISTANCE = 150
const POINTER_RADIUS = 280
const MAX_SPEED = 0.72
const SEPARATION_PASSES = 3

const canvas = ref<HTMLCanvasElement>()
let frame = 0
let removeListeners: (() => void) | undefined

function wrap(value: number, limit: number) {
  return (value + limit) % limit
}

onMounted(() => {
  const node = canvas.value!
  const context = node.getContext('2d')!
  const pointer = { x: 0, y: 0, active: false }
  const particles: Particle[] = []
  let width = innerWidth
  let height = innerHeight
  let previousTime = performance.now()

  const createParticle = (): Particle => {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const candidate = {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - .5) * .24,
        vy: (Math.random() - .5) * .24,
      }
      if (particles.every((particle) => Math.hypot(candidate.x - particle.x, candidate.y - particle.y) >= MIN_DISTANCE)) return candidate
    }
    return { x: Math.random() * width, y: Math.random() * height, vx: 0, vy: 0 }
  }

  const resize = () => {
    const previousWidth = width
    const previousHeight = height
    width = innerWidth
    height = innerHeight
    const pixelRatio = Math.min(devicePixelRatio, 2)
    node.width = Math.round(width * pixelRatio)
    node.height = Math.round(height * pixelRatio)
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    if (particles.length) {
      particles.forEach((particle) => {
        particle.x *= width / previousWidth
        particle.y *= height / previousHeight
      })
    } else {
      while (particles.length < PARTICLE_COUNT) particles.push(createParticle())
    }
  }

  const movePointer = (event: PointerEvent) => {
    pointer.x = event.clientX
    pointer.y = event.clientY
    pointer.active = true
  }
  const releasePointer = () => { pointer.active = false }

  const separateParticles = () => {
    for (let pass = 0; pass < SEPARATION_PASSES; pass += 1) {
      for (let first = 0; first < particles.length; first += 1) {
        for (let second = first + 1; second < particles.length; second += 1) {
          const a = particles[first]!
          const b = particles[second]!
          let dx = b.x - a.x
          let dy = b.y - a.y
          let distance = Math.hypot(dx, dy)
          if (distance >= MIN_DISTANCE) continue
          if (distance < .001) {
            const angle = Math.random() * Math.PI * 2
            dx = Math.cos(angle)
            dy = Math.sin(angle)
            distance = 1
          }
          const nx = dx / distance
          const ny = dy / distance
          const correction = (MIN_DISTANCE - distance) * .5
          a.x -= nx * correction
          a.y -= ny * correction
          b.x += nx * correction
          b.y += ny * correction
          a.vx -= nx * .008
          a.vy -= ny * .008
          b.vx += nx * .008
          b.vy += ny * .008
        }
      }
      particles.forEach((particle) => {
        particle.x = wrap(particle.x, width)
        particle.y = wrap(particle.y, height)
      })
    }
  }

  const draw = (time: number) => {
    const timeScale = Math.min(2, Math.max(.35, (time - previousTime) / 16.67))
    previousTime = time
    context.clearRect(0, 0, width, height)

    particles.forEach((particle) => {
      if (pointer.active) {
        const dx = pointer.x - particle.x
        const dy = pointer.y - particle.y
        const distance = Math.hypot(dx, dy)
        if (distance > 1 && distance < POINTER_RADIUS) {
          const falloff = 1 - distance / POINTER_RADIUS
          const force = .013 * falloff * falloff * timeScale
          particle.vx += dx / distance * force
          particle.vy += dy / distance * force
        }
      }

      const damping = Math.pow(.994, timeScale)
      particle.vx *= damping
      particle.vy *= damping
      const speed = Math.hypot(particle.vx, particle.vy)
      if (speed > MAX_SPEED) {
        particle.vx = particle.vx / speed * MAX_SPEED
        particle.vy = particle.vy / speed * MAX_SPEED
      }
      particle.x = wrap(particle.x + particle.vx * timeScale, width)
      particle.y = wrap(particle.y + particle.vy * timeScale, height)
    })

    separateParticles()

    for (let first = 0; first < particles.length; first += 1) {
      for (let second = first + 1; second < particles.length; second += 1) {
        const a = particles[first]!
        const b = particles[second]!
        const distance = Math.hypot(a.x - b.x, a.y - b.y)
        if (distance >= MIN_DISTANCE && distance < LINK_DISTANCE) {
          context.strokeStyle = `rgba(40, 196, 239, ${.28 * (1 - distance / LINK_DISTANCE)})`
          context.lineWidth = 1.2
          context.beginPath()
          context.moveTo(a.x, a.y)
          context.lineTo(b.x, b.y)
          context.stroke()
        }
      }
    }

    particles.forEach((particle) => {
      context.fillStyle = 'rgba(91, 225, 255, .72)'
      context.beginPath()
      context.arc(particle.x, particle.y, 2.2, 0, Math.PI * 2)
      context.fill()
    })
    frame = requestAnimationFrame(draw)
  }

  resize()
  addEventListener('resize', resize)
  addEventListener('pointermove', movePointer, { passive: true })
  document.documentElement.addEventListener('pointerleave', releasePointer)
  addEventListener('blur', releasePointer)
  removeListeners = () => {
    removeEventListener('resize', resize)
    removeEventListener('pointermove', movePointer)
    document.documentElement.removeEventListener('pointerleave', releasePointer)
    removeEventListener('blur', releasePointer)
  }
  frame = requestAnimationFrame(draw)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  removeListeners?.()
})
</script>

<template><canvas ref="canvas" class="particle-field" aria-hidden="true" /></template>
