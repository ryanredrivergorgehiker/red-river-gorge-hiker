import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const initialized = new WeakSet();

const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

async function setup(shell) {
  const canvas = shell.querySelector('[data-route-map]');
  if (!canvas || initialized.has(canvas)) return;
  initialized.add(canvas);

  const configNode = shell.querySelector('script[type="application/json"]');
  const config = JSON.parse(configNode.textContent);
  const status = shell.querySelector('[data-map-status]');
  const layerDefs = new Map(config.layers.map((layer) => [layer.id, layer]));
  const map = L.map(canvas, {
    scrollWheelZoom: config.mode === 'full',
    keyboard: true,
    zoomControl: true
  });

  const tileLayers = new Map();
  let activeBase = null;
  const activeOverlays = new Map();
  let waypointMinZoom = 13;
  let showWaypoints = true;
  const routeRecords = [];

  const makeTile = (def, opacity = 1) => {
    if (tileLayers.has(def.id)) return tileLayers.get(def.id);
    const layer = L.tileLayer(def.url, {
      maxZoom: def.maxZoom ?? 19,
      minZoom: def.minZoom ?? 0,
      opacity,
      attribution: def.attribution
    });
    layer.on('tileerror', () => {
      if (status) status.textContent = 'Some map tiles could not be loaded. The approved RRGH route geometry remains available.';
    });
    tileLayers.set(def.id, layer);
    return layer;
  };

  const setBase = (id) => {
    const def = layerDefs.get(id);
    if (!def || !def.enabled || def.kind !== 'base') return;
    if (activeBase) map.removeLayer(activeBase);
    activeBase = makeTile(def);
    activeBase.addTo(map);
    const select = shell.querySelector('[data-map-base]');
    if (select) select.value = id;
  };

  const setOverlay = (id, on) => {
    const def = layerDefs.get(id);
    if (!def || !def.enabled || def.kind !== 'overlay') return;
    const checkbox = shell.querySelector(`[data-map-overlay="${id}"]`);
    if (checkbox) checkbox.checked = on;
    if (on) {
      const layer = makeTile(def, def.defaultOpacity ?? 0.6);
      activeOverlays.set(id, layer);
      if (!map.hasLayer(layer)) layer.addTo(map);
    } else if (activeOverlays.has(id)) {
      map.removeLayer(activeOverlays.get(id));
      activeOverlays.delete(id);
    }
  };

  const updateRouteVisibility = () => {
    const enabledTrips = new Set([...shell.querySelectorAll('[data-route-filter]:checked')].map((node) => node.dataset.routeFilter));
    const enabledTrails = new Set([...shell.querySelectorAll('[data-trail-filter]:checked')].map((node) => node.dataset.trailFilter));
    for (const record of routeRecords) {
      const allowed = config.mode !== 'full'
        || (enabledTrips.has(record.meta.tripType) && enabledTrails.has(record.meta.trailStatus));
      if (allowed && !map.hasLayer(record.line)) record.line.addTo(map);
      if (!allowed && map.hasLayer(record.line)) map.removeLayer(record.line);
    }
    updateWaypoints();
  };

  const updateWaypoints = () => {
    const visibleAtZoom = map.getZoom() >= waypointMinZoom;
    for (const record of routeRecords) {
      const routeVisible = map.hasLayer(record.line);
      for (const marker of record.markers) {
        if (showWaypoints && visibleAtZoom && routeVisible) {
          if (!map.hasLayer(marker)) marker.addTo(map);
        } else if (map.hasLayer(marker)) map.removeLayer(marker);
      }
    }
  };

  setBase('kytopo');

  const bounds = L.latLngBounds();
  for (const route of config.routes) {
    try {
      const response = await fetch(route.geometryUrl, { credentials: 'omit' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const geojson = await response.json();
      const lineFeatures = geojson.features.filter((feature) => feature.geometry?.type === 'LineString' || feature.geometry?.type === 'MultiLineString');
      const line = L.geoJSON(lineFeatures, {
        style: {
          color: route.publicationClass === 'C' ? '#9a4f2c' : '#163f34',
          weight: 5,
          opacity: 0.92
        }
      });
      line.eachLayer((layer) => {
        if (layer.getBounds) bounds.extend(layer.getBounds());
      });
      line.bindPopup(`<strong>${escapeText(route.title)}</strong><br><a href="${config.base}routes/${encodeURIComponent(route.slug)}/">Route details</a>`);
      line.addTo(map);

      const markers = route.waypoints.map((point) => {
        const marker = L.marker([point.lat, point.lon], {
          keyboard: true,
          title: point.name,
          alt: point.name,
          icon: L.divIcon({
            className: 'rrgh-waypoint-icon-wrap',
            html: '<span class="rrgh-waypoint-icon" aria-hidden="true"></span>',
            iconSize: [18, 18],
            iconAnchor: [9, 9]
          })
        });
        marker.bindPopup(`<strong>${escapeText(point.name)}</strong><br>${escapeText(point.type)}${point.description ? `<br>${escapeText(point.description)}` : ''}`);
        return marker;
      });
      routeRecords.push({ meta: route, line, markers });
    } catch (error) {
      if (status) status.textContent = `Route geometry could not be loaded: ${route.title}.`;
    }
  }

  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(config.mode === 'full' ? 0.18 : 0.12), { maxZoom: config.mode === 'full' ? 14 : 16 });
  } else {
    map.setView([37.8184, -83.5798], 14);
  }
  updateWaypoints();

  map.on('zoomend', updateWaypoints);

  shell.querySelectorAll('[data-map-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const preset = config.presets.find((item) => item.id === button.dataset.mapPreset);
      if (!preset) return;
      setBase(preset.baseLayerId);
      for (const def of config.layers.filter((item) => item.kind === 'overlay' && item.enabled)) {
        setOverlay(def.id, preset.overlayLayerIds.includes(def.id));
      }
      waypointMinZoom = preset.waypointMinZoom;
      updateWaypoints();
      shell.querySelectorAll('[data-map-preset]').forEach((node) => node.classList.toggle('is-active', node === button));
      if (status) status.textContent = `${preset.label}: ${preset.note}`;
    });
  });

  shell.querySelector('[data-map-base]')?.addEventListener('change', (event) => setBase(event.target.value));
  shell.querySelectorAll('[data-map-overlay]').forEach((input) => input.addEventListener('change', () => setOverlay(input.dataset.mapOverlay, input.checked)));
  shell.querySelector('[data-map-waypoints]')?.addEventListener('change', (event) => {
    showWaypoints = event.target.checked;
    updateWaypoints();
  });
  shell.querySelectorAll('[data-route-filter], [data-trail-filter]').forEach((input) => input.addEventListener('change', updateRouteVisibility));

  const gate = shell.querySelector('[data-map-enable]');
  gate?.addEventListener('click', () => {
    map.scrollWheelZoom.enable();
    canvas.focus();
    gate.textContent = 'Map wheel zoom enabled — press Escape to disable';
  });
  canvas.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && config.mode !== 'full') {
      map.scrollWheelZoom.disable();
      if (gate) gate.textContent = 'Enable map wheel zoom';
      gate?.focus();
    }
  });

  shell.querySelector('[data-map-preset="simple"]')?.click();
  setTimeout(() => map.invalidateSize(), 0);
}

document.querySelectorAll('.route-map-shell').forEach((shell) => setup(shell));
