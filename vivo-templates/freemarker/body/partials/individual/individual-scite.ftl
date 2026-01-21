<#-- $This file is distributed under the terms of the license in LICENSE$ -->

<#-- Scite badge on individual profile page -->

<#if sciteEnabled??>
    <#assign doi = propertyGroups.getProperty("http://purl.org/ontology/bibo/doi")!>
    <#if doi?has_content> <#-- true when the property is in the list, even if not populated (when editing) -->
        <#if doi.statements[0]??>
            <div class="individual-scite-badge">
                <div class="scite-badge"
                     style="float: ${sciteDisplayTo}; padding-left: 15px; padding-right: 15px;"
                     data-doi="${doi.statements[0].value}"
                     data-layout="${sciteLayout!"horizontal"}"
                     <#if sciteShowZero??>data-show-zero="${sciteShowZero}"<#else>data-show-zero="false"</#if>
                     <#if sciteSmall??>data-small="${sciteSmall}"<#else>data-small="false"</#if>
                     <#if sciteShowLabels??>data-show-labels="${sciteShowLabels}"<#else>data-show-labels="false"</#if>
                     <#if sciteTallyShow??>data-tally-show="${sciteTallyShow}"<#else>data-tally-show="true"</#if>>
                </div>
            </div>
        </#if>
    </#if>
</#if>
