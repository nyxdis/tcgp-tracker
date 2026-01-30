// Theme management functionality
class ThemeManager {
  constructor() {
    this.storageKey = 'tcgp-tracker-theme';
    this.init();
  }

  init() {
    // Get saved theme preference (light, dark, auto) or default to auto
    const savedTheme = localStorage.getItem(this.storageKey) || 'auto';
    this.setTheme(savedTheme);

    // Set up event listeners
    this.setupEventListeners();
  }

  getSystemPreference() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  getActualTheme(theme) {
    if (theme === 'auto') {
      return this.getSystemPreference();
    }
    return theme;
  }

  setupEventListeners() {
    const toggleButton = document.getElementById('theme-toggle');

    if (toggleButton) {
      toggleButton.addEventListener('click', () => this.toggleTheme());
    }

    // Listen for system theme changes
    if (window.matchMedia) {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', () => {
        // Only respond to system changes if in auto mode
        if (this.getCurrentTheme() === 'auto') {
          this.setTheme('auto'); // Re-apply auto to pick up new system preference
        }
      });
    }
  }

  getCurrentTheme() {
    return localStorage.getItem(this.storageKey) || 'auto';
  }

  setTheme(theme) {
    const actualTheme = this.getActualTheme(theme);
    document.documentElement.setAttribute('data-theme', actualTheme);
    localStorage.setItem(this.storageKey, theme);
    this.updateToggleButton(theme);
  }

  toggleTheme() {
    const currentTheme = this.getCurrentTheme();
    let newTheme;

    switch (currentTheme) {
      case 'light':
        newTheme = 'dark';
        break;
      case 'dark':
        newTheme = 'auto';
        break;
      case 'auto':
      default:
        newTheme = 'light';
        break;
    }

    this.setTheme(newTheme);
  }

  updateToggleButton(theme) {
    const toggleButton = document.getElementById('theme-toggle');
    const sunIcon = document.getElementById('sun-icon');
    const moonIcon = document.getElementById('moon-icon');
    const autoIcon = document.getElementById('auto-icon');

    if (toggleButton && sunIcon && moonIcon && autoIcon) {
      // Hide all icons first
      sunIcon.classList.add('hidden');
      sunIcon.classList.remove('visible');
      moonIcon.classList.add('hidden');
      moonIcon.classList.remove('visible');
      autoIcon.classList.add('hidden');
      autoIcon.classList.remove('visible');

      switch (theme) {
        case 'light':
          sunIcon.classList.remove('hidden');
          sunIcon.classList.add('visible');
          toggleButton.title = 'Light mode (click for dark)';
          break;
        case 'dark':
          moonIcon.classList.remove('hidden');
          moonIcon.classList.add('visible');
          toggleButton.title = 'Dark mode (click for auto)';
          break;
        case 'auto':
        default:
          autoIcon.classList.remove('hidden');
          autoIcon.classList.add('visible');
          toggleButton.title = 'Auto mode (click for light)';
          break;
      }
    }
  }
}

// Initialize theme manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  new ThemeManager();
});

// Also initialize immediately if DOM is already loaded
if (document.readyState !== 'loading') {
  new ThemeManager();
}
