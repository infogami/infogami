
$(document).ready(function() {
    jQuery('input[@infogami_autocomplete=true]').each(function(){

        var thingtype = jQuery(this).attr('thingtype')
        var maxlimit  = jQuery(this).attr('limit')
        
        jQuery(this).autocomplete("/getthings", {
            extraParams: {type: thingtype }, 
            max: maxlimit 
        });
    });
});
