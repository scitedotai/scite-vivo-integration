# VIVO Template Files for Scite Badge Integration

This directory contains the Freemarker templates and configuration needed to display Scite badges on VIVO publication pages.

## Files

### Freemarker Templates

1. **`freemarker/body/partials/individual/individual-scite.ftl`**
   - Renders the Scite badge widget on publication pages
   - Checks for DOI presence before rendering
   - Configurable via runtime.properties

2. **`freemarker/body/individual/individual.ftl`**
   - Modified main individual page template
   - Includes the Scite badge template
   - Loads Scite JavaScript library

### Configuration

3. **`runtime.properties.scite`**
   - Scite badge configuration properties
   - Add these to your `$VIVO_HOME/config/runtime.properties`

## Installation

### Option 1: Build into VIVO (Recommended)

1. Copy template files to your VIVO home directory:
   ```bash
   cp -r freemarker/ $VIVO_HOME/src/main/resources/templates/
   ```

2. Add Scite configuration to runtime.properties:
   ```bash
   cat runtime.properties.scite >> $VIVO_HOME/config/runtime.properties
   ```

3. Rebuild VIVO:
   ```bash
   cd $VIVO_INSTALL/VIVO
   mvn install -s installer/settings.xml -DskipTests
   ```

4. Restart Tomcat:
   ```bash
   # macOS with Homebrew
   brew services restart tomcat@9

   # Linux systemd
   sudo systemctl restart tomcat9
   ```

### Option 2: Deploy Directly to Running VIVO

1. Copy templates to deployed webapp:
   ```bash
   cp freemarker/body/partials/individual/individual-scite.ftl \
      $TOMCAT_HOME/webapps/vivo/templates/freemarker/body/partials/individual/

   cp freemarker/body/individual/individual.ftl \
      $TOMCAT_HOME/webapps/vivo/templates/freemarker/body/individual/
   ```

2. Add configuration to runtime.properties:
   ```bash
   cat runtime.properties.scite >> $VIVO_HOME/config/runtime.properties
   ```

3. Restart Tomcat (templates will be reloaded)

## Configuration Options

Edit the Scite properties in `runtime.properties` to customize badge appearance:

| Property | Values | Description |
|----------|--------|-------------|
| `resource.scite` | `enabled` / disabled | Enable/disable Scite badges |
| `resource.scite.displayto` | `left` / `right` | Badge position |
| `resource.scite.layout` | `horizontal` / `vertical` | Badge orientation |
| `resource.scite.show-zero` | `true` / `false` | Show badge when citation count is zero |
| `resource.scite.small` | `true` / `false` | Use compact badge size |
| `resource.scite.show-labels` | `true` / `false` | Show text labels for citation types |
| `resource.scite.tally-show` | `true` / `false` | Display numeric tallies |

## How It Works

1. When a user views a publication page in VIVO, the `individual.ftl` template is rendered
2. If Scite badges are enabled and the publication has a DOI, `individual-scite.ftl` is included
3. The template outputs a `<div>` with `class="scite-badge"` and the DOI in `data-doi` attribute
4. The Scite JavaScript library (loaded from CDN) finds these divs and renders interactive badges
5. Users can click badges to see detailed citation context on scite.ai

## Troubleshooting

### Badges not appearing

1. **Check runtime.properties**: Ensure `resource.scite=enabled`
2. **Verify templates**: Confirm template files are in the correct location
3. **Check publication DOI**: Badges only appear for publications with valid DOIs
4. **Browser console**: Look for JavaScript errors that might prevent badge rendering
5. **Clear cache**: Try clearing browser cache and reloading the page

### Badge shows "No citations"

This is normal - it means the paper hasn't been cited yet or Scite hasn't indexed citations for it.

## Support

For issues with:
- **Scite badges**: https://scite.ai/badge
- **VIVO templates**: https://wiki.lyrasis.org/display/VIVODOC115x/
- **This integration**: https://github.com/scitedotai/scite-vivo-integration/issues
