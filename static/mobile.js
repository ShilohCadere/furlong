/* Shared responsive navigation. Links remain available when JavaScript is off. */
(() => {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const menus = [...sidebar.querySelectorAll('nav')];
    if (!menus.length) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'mobile-menu-toggle';
    button.textContent = 'Menu';
    button.setAttribute('aria-label', 'Open navigation');
    menus.forEach((menu, index) => {
        if (!menu.id) menu.id = `furlong-navigation-${index}`;
    });
    button.setAttribute('aria-controls', menus.map(menu => menu.id).join(' '));
    sidebar.insertBefore(button, menus[0]);
    sidebar.classList.add('mobile-navigation-ready');
    const narrow = window.matchMedia('(max-width: 680px)');
    function setOpen(open, restoreFocus = false) {
        sidebar.classList.toggle('mobile-menu-open', open);
        button.setAttribute('aria-expanded', String(open));
        button.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
        button.textContent = open ? 'Close' : 'Menu';
        menus.forEach(menu => { menu.hidden = narrow.matches && !open; });
        if (restoreFocus) button.focus();
    }
    button.addEventListener('click', () => setOpen(button.getAttribute('aria-expanded') !== 'true'));
    sidebar.addEventListener('keydown', event => {
        if (event.key === 'Escape' && narrow.matches) setOpen(false, true);
    });
    sidebar.addEventListener('click', event => {
        const link = event.target.closest('nav a');
        if (link && narrow.matches) {
            setOpen(false);
            // Same-page jumps should move keyboard focus along with the viewport.
            if (link.hash && link.pathname === location.pathname) {
                const target = document.getElementById(decodeURIComponent(link.hash.slice(1)));
                if (target) { target.tabIndex = -1; target.focus({preventScroll:true}); }
            }
        }
    });
    narrow.addEventListener('change', () => {
        const hadFocus = sidebar.contains(document.activeElement);
        setOpen(false, narrow.matches && hadFocus);
    });
    setOpen(false);
})();
