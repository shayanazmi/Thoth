/**
 * Thoth · Anime.js & 3D Parallax Animation Engine
 * Precision micro-interactions, spring accordions, and fluid view morphing
 */

const ThothAnimations = {
  init3DParallax() {
    const cards = document.querySelectorAll('.card-3d');
    
    cards.forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        
        const rotateX = ((y - centerY) / centerY) * -8;
        const rotateY = ((x - centerX) / centerX) * 8;
        
        card.style.transform = `perspective(1200px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateZ(10px)`;
        
        const glare = card.querySelector('.card-3d-glare');
        if (glare) {
          glare.style.background = `radial-gradient(circle at ${(x / rect.width * 100).toFixed(0)}% ${(y / rect.height * 100).toFixed(0)}%, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0) 60%)`;
        }
      });
      
      card.addEventListener('mouseleave', () => {
        card.style.transform = `perspective(1200px) rotateX(0deg) rotateY(0deg) translateZ(0px)`;
      });
    });
  },

  animateViewTransition(fromViewEl, toViewEl, onComplete) {
    if (typeof anime === 'undefined') {
      fromViewEl.classList.add('hidden');
      toViewEl.classList.remove('hidden');
      if (onComplete) onComplete();
      return;
    }

    anime({
      targets: fromViewEl,
      opacity: [1, 0],
      scale: [1, 0.96],
      duration: 250,
      easing: 'easeInOutQuad',
      complete: () => {
        fromViewEl.classList.add('hidden');
        toViewEl.classList.remove('hidden');
        
        anime({
          targets: toViewEl,
          opacity: [0, 1],
          scale: [0.98, 1],
          duration: 350,
          easing: 'easeOutCubic',
          complete: () => {
            if (onComplete) onComplete();
          }
        });
      }
    });
  },

  pulseActiveNode(nodeElement) {
    if (!nodeElement || typeof anime === 'undefined') return;
    
    anime({
      targets: nodeElement,
      scale: [1, 1.06, 1],
      boxShadow: [
        '0 0 0px rgba(201, 154, 107, 0)',
        '0 0 16px rgba(201, 154, 107, 0.5)',
        '0 0 0px rgba(201, 154, 107, 0)'
      ],
      duration: 1200,
      loop: true,
      easing: 'easeInOutSine'
    });
  },

  animateAccordion(contentEl, isOpen) {
    if (!contentEl) return;
    
    if (isOpen) {
      contentEl.classList.remove('hidden');
      if (typeof anime !== 'undefined') {
        anime({
          targets: contentEl,
          opacity: [0, 1],
          height: [0, contentEl.scrollHeight],
          duration: 300,
          easing: 'easeOutCubic'
        });
      }
    } else {
      if (typeof anime !== 'undefined') {
        anime({
          targets: contentEl,
          opacity: [1, 0],
          height: [contentEl.scrollHeight, 0],
          duration: 250,
          easing: 'easeInOutQuad',
          complete: () => contentEl.classList.add('hidden')
        });
      } else {
        contentEl.classList.add('hidden');
      }
    }
  },

  animateNewMessage(messageEl) {
    if (!messageEl || typeof anime === 'undefined') return;
    
    anime({
      targets: messageEl,
      opacity: [0, 1],
      translateY: [16, 0],
      duration: 350,
      easing: 'easeOutCubic'
    });
  }
};

window.ThothAnimations = ThothAnimations;
