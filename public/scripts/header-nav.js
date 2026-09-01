(() => {
  const header = document.querySelector('.site-header');
  if (!header) return;

  const desktopMedia = window.matchMedia('(min-width: 851px) and (hover: hover)');
  const mobileMedia = window.matchMedia('(max-width: 850px)');
  const desktopMenus = Array.from(header.querySelectorAll('.desktop-nav .nav-details'));
  const mobileMenus = Array.from(header.querySelectorAll('.mobile-primary-nav .nav-details'));

  const positionMobileMenu = (menu) => {
    if (!mobileMedia.matches || !menu.open) return;

    const nav = menu.closest('.mobile-primary-nav');
    const trigger = menu.querySelector('.nav-trigger');
    const panel = menu.querySelector('.nav-panel');
    if (!nav || !trigger || !panel) return;

    panel.style.setProperty('--mobile-panel-left', '0px');

    requestAnimationFrame(() => {
      const navRect = nav.getBoundingClientRect();
      const triggerRect = trigger.getBoundingClientRect();
      const panelRect = panel.getBoundingClientRect();
      const desiredLeft = triggerRect.left - navRect.left;
      const maxLeft = Math.max(0, navRect.width - panelRect.width);
      const clampedLeft = Math.min(Math.max(0, desiredLeft), maxLeft);
      panel.style.setProperty('--mobile-panel-left', `${clampedLeft}px`);
    });
  };

  desktopMenus.forEach((menu) => {
    menu.addEventListener('mouseenter', () => {
      if (desktopMedia.matches) menu.open = true;
    });

    menu.addEventListener('mouseleave', () => {
      if (desktopMedia.matches) menu.open = false;
    });

    menu.addEventListener('focusout', () => {
      if (!desktopMedia.matches) return;
      requestAnimationFrame(() => {
        if (!menu.contains(document.activeElement)) menu.open = false;
      });
    });
  });

  mobileMenus.forEach((menu) => {
    menu.addEventListener('toggle', () => {
      if (menu.open) positionMobileMenu(menu);
    });
  });

  const repositionOpenMobileMenu = () => {
    if (!mobileMedia.matches) return;
    mobileMenus.forEach((menu) => {
      if (menu.open) positionMobileMenu(menu);
    });
  };

  window.addEventListener('resize', repositionOpenMobileMenu, { passive: true });
  window.addEventListener('orientationchange', repositionOpenMobileMenu);
})();
