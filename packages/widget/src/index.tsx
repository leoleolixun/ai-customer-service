import React from 'react';
import { createRoot, type Root } from 'react-dom/client';

import Widget from './Widget';
import { parseWidgetLanguage, type WidgetLanguage } from './i18n';
import styles from './widget.css?inline';

export { default as Widget } from './Widget';
export type { WidgetProps } from './Widget';
export type { WidgetLanguage } from './i18n';

export class AISupportWidgetElement extends HTMLElement {
  private root: Root | null = null;
  private mount: HTMLDivElement | null = null;
  private tokenValue = '';
  tokenProvider: (() => string | Promise<string>) | null = null;

  static get observedAttributes(): string[] {
    return ['base-url', 'application-id', 'session-key', 'token', 'title', 'welcome', 'language'];
  }

  connectedCallback(): void {
    this.tokenValue = this.getAttribute('token') ?? this.tokenValue;
    const shadow = this.shadowRoot ?? this.attachShadow({ mode: 'open' });
    if (!this.mount) {
      const style = document.createElement('style');
      style.textContent = styles;
      this.mount = document.createElement('div');
      shadow.replaceChildren(style, this.mount);
    }
    this.root ??= createRoot(this.mount);
    this.renderWidget();
  }

  disconnectedCallback(): void {
    this.root?.unmount();
    this.root = null;
    this.mount = null;
  }

  attributeChangedCallback(): void {
    if (this.isConnected) {
      this.tokenValue = this.getAttribute('token') ?? this.tokenValue;
      this.renderWidget();
    }
  }

  setToken(token: string): void {
    this.tokenValue = token;
    this.renderWidget();
  }

  private renderWidget(): void {
    const baseUrl = this.getAttribute('base-url') ?? window.location.origin;
    const applicationId = this.getAttribute('application-id') ?? 'default';
    const getToken = async (): Promise<string> => {
      const token = this.tokenProvider ? await this.tokenProvider() : this.tokenValue;
      if (!token) throw new Error('A short-lived customer token is required.');
      return token;
    };
    this.root?.render(
      <Widget
        baseUrl={baseUrl}
        applicationId={applicationId}
        getToken={getToken}
        sessionKey={this.getAttribute('session-key') ?? undefined}
        title={this.getAttribute('title') ?? undefined}
        welcome={this.getAttribute('welcome') ?? undefined}
        language={parseWidgetLanguage(this.getAttribute('language'))}
        onLanguageChange={(language: WidgetLanguage) => {
          if (this.getAttribute('language') !== language) {
            this.setAttribute('language', language);
          }
        }}
      />,
    );
  }
}

if (!customElements.get('ai-support-widget')) {
  customElements.define('ai-support-widget', AISupportWidgetElement);
}

const script = document.currentScript as HTMLScriptElement | null;
if (script?.dataset.baseUrl && !document.querySelector('ai-support-widget')) {
  const element = document.createElement('ai-support-widget');
  element.setAttribute('base-url', script.dataset.baseUrl);
  if (script.dataset.applicationId) {
    element.setAttribute('application-id', script.dataset.applicationId);
  }
  if (script.dataset.sessionKey) element.setAttribute('session-key', script.dataset.sessionKey);
  if (script.dataset.token) element.setAttribute('token', script.dataset.token);
  if (script.dataset.title) element.setAttribute('title', script.dataset.title);
  if (script.dataset.welcome) element.setAttribute('welcome', script.dataset.welcome);
  if (script.dataset.language) element.setAttribute('language', script.dataset.language);
  document.body.append(element);
}
