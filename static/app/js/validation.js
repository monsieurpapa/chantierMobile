$(document).ready(function() {
  $.validator.setDefaults({
    focusCleanup: true,
    focusInvalid: false,
    onclick: false,
    onfocusout: false,
    ignore: ".ignore",
    errorElement: 'div',
    onkeyup: function(element, event) {
      if (event.keyCode == 13) {
        $(element).blur();
      }
    },
    rules: {
      phone: {
        minlength: 9
      },
      password1: {
        minlength: 8
      },
      password2: {
        minlength: 8,
        equalTo: "#id_password1"
      }
    },
    errorPlacement: function(error, element) {
     // error.insertAfter(element);
     element.parents('.form-group').append(error);
     //console.log(element);
    }
  });
  $.validator.addMethod("regx", function(value, element, regexpr) {          
    return regexpr.test(value);
  }, "Please enter a valid phone number.");

  // Form Validation
  $('#frm-acc-reg-1, #frm-acc-reg-2, #frm-acc-reg-3, #frm-acc-reg-4, #frm-acc-reg-5, #frm-acc-reg-6, #frm-acc-reg-7, #frm-acc-reg-8').validate({
    rules: {
      email: {
        remote: {
          url: window.location.protocol + "//" + window.location.host + "/user/validate-email/",
          type: 'get'
        }
      }
    },
    messages: {
      email: {
        remote: 'A user with this email address already exists.'
      }
    }
  });

  $('#frmLogin').validate();

  // $('#frmLogin').validate({
  //   submitHandler: function(form) {
  //     $('#frmLogin button[type="submit"]').hide();
  //
  //     $(form).ajaxSubmit({
  //       success: function(data){
  //         $('#frmLogin').parent().html(data.message);
  //         if(!data.success){
  //           console.log(data.form_errors);
  //         }
  //       }
  //    });
  //   }
  // });

  $('#frmFeedbackForm').validate({
    submitHandler: function(form) {
      $('#frmFeedbackForm button[type="submit"]').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmFeedbackForm').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });


  $('#frmApprovalForm').validate({
    onfocusout: false,
    onkeyup: false,
    submitHandler: function(form) {

      $('#frmApprovalForm button[type="submit"]').hide();
      $(form).ajaxSubmit({
          success: function(data){
          $('#frmApprovalForm').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('.frmUpdateContact').each(function() {
    $(this).validate({
      submitHandler: function(form) {
        var action = $(this).attr('action');
        $(form).ajaxSubmit({
          url: action,
          success: function(data) {
            window.location.reload();
          }
        });
      },
      rules: {
        contact_number: {
          minlength: 9
        },
        phone: {
          minlength: 9,
          regx: /^(\+?)[0-9\s]{9,16}$/,
        }
      },
    });
  });

  $('#frmMainContact').validate({
    rules: {
      email: {
          required: true,
          remote: {
            url: window.location.protocol + "//" + window.location.host + "/validate-email/",
            type: 'get'
          }
      },
    },
    messages: {
      email: {
        remote: $.validator.format("This email address already exists.")
      }
    },
    submitHandler: function(form) {
      var action = $(this).attr('action');
      $(form).ajaxSubmit({
        url: action,
        success: function(data) {
          window.location.reload();
        }
      });
    }
  });

  $('#frmContactModal').validate();

  $('#frmBusinessProfile').validate();

  $('#frmCompanyDetails').validate();

  $('#frmAuthorisedBankContact').validate();

  $('#frmInstallationContact').validate();

  $('#frmBillingContact').validate();

  $('#frmBillingContact2').validate();

  $('#frmBillingAddress').validate({
    submitHandler: function(form) {
      $(form).ajaxSubmit({
        success: function(data){
          $('#frmBillingAddress').parent().html(data.message);
          $('#modal-billing-address').find('.modal-title').html('Thank you');
          dialog = $('#modal-billing-address').find('.modal-dialog');
          dialog.css("margin-top", Math.max(0, ($(window).height() - dialog.height()) / 2));
          setTimeout(function() {
            $('#modal-billing-address').modal('toggle');
          }, 3000);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmAuditorsBankDetails').validate();

  $('#frmNewOrder').validate({
    submitHandler: function(form) {
      $('#frmNewOrder button[type="submit"]').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmNewOrder').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

    // Validation
  $('#frmInterestedForm').validate({
    submitHandler: function(form) {

      // $('#contact-form button').hide();
      // $('#contact-form #submit-spinner').show();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmInterestedForm').parent().html(data.message);
        },
        error: function(data){
          console.log('error');
          console.log(data);
        }
      });
    },
    rules: {
        phone: {
          minlength: 9,
          regx: /^(\+?)[0-9\s]{9,16}$/,
        },
      },
  });

  $('#frmForgottenPassword').validate({
    // submitHandler: function(form) {
    //   $('#frmForgottenPassword button').hide();

    //   $(form).ajaxSubmit({
    //     success: function(data){
    //       $('#frmForgottenPassword').parent().html(data.message);
    //       if(!data.success){
    //         console.log(data.form_errors);
    //       }
    //     }
    //  });
    // }
  });

  $('#plan-signup').validate({
    submitHandler: function(form) {
      $('#plan-signup button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#plan-signup').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmChangePassword').validate({
    submitHandler: function(form) {
      $(form).ajaxSubmit({
        success: function(data){
          $('#frmChangePassword').parent().html(data.message);
          $('#modal-change-password').find('.modal-title').html('Thank you');
          dialog = $('#modal-change-password').find('.modal-dialog');
          dialog.css("margin-top", Math.max(0, ($(window).height() - dialog.height()) / 2));
          setTimeout(function() {
            $('#modal-change-password').modal('toggle');
          }, 3000);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmAccountRegistration').validate({
    messages: {
      country_code: "Required"
    }
  });

  $('#frmSetPassword').validate();

  $('#frmSetExpiredPassword').validate();

  function reposition() {
        var modal = $(this),
            dialog = modal.find('.modal-dialog');
        modal.css('display', 'block');

        // Dividing by two centers the modal exactly, but dividing by three 
        // or four works better for larger screens.
        dialog.css("margin-top", Math.max(0, ($(window).height() - dialog.height()) / 2));
    }

  $('#frmDebitChange').validate({
    submitHandler: function(form) {

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmDebitChange').parent().html(data.message);
          $('#modal-debit-change').find('.modal-title').html('Thank you');
          dialog = $('#modal-debit-change').find('.modal-dialog');
          dialog.css("margin-top", Math.max(0, ($(window).height() - dialog.height()) / 2));
          setTimeout(function() {
            $('#modal-debit-change').modal('toggle');
          }, 3000);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmIssuesComment').validate();

  $('#all-issues-attachments').validate({
    submitHandler: function(form) {
      var action = $(this).attr('action');
      $(form).ajaxSubmit({
        url: action,
        success: function(data) {
          window.location.reload();
        }
      });
    }
  });

  $('#frmProductBroadband').validate({
    submitHandler: function(form) {
      $('#frmProductBroadband button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductBroadband').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductCorporate').validate({
    submitHandler: function(form) {
      $('#frmProductCorporate button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductCorporate').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductDirectAccess').validate({
    submitHandler: function(form) {
      $('#frmProductDirectAccess button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductDirectAccess').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductHostedMail').validate({
    submitHandler: function(form) {
      $('#frmProductHostedMail button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductHostedMail').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductHostedSecurity').validate({
    submitHandler: function(form) {
      $('#frmProductHostedSecurity button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductHostedSecurity').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductOnlineBackup').validate({
    submitHandler: function(form) {
      $('#frmProductOnlineBackup button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductOnlineBackup').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductSeacomVoice').validate({
    submitHandler: function(form) {
      $('#frmProductSeacomVoice button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductSeacomVoice').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductSymantec').validate({
    submitHandler: function(form) {
      $('#frmProductSymantec button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductSymantec').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductWireless').validate({
    submitHandler: function(form) {
      $('#frmProductWireless button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductWireless').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmProductVlan').validate({
    submitHandler: function(form) {
      $('#frmProductVlan button').hide();

      $(form).ajaxSubmit({
        success: function(data){
          $('#frmProductVlan').parent().html(data.message);
          if(!data.success){
            console.log(data.form_errors);
          }
        }
     });
    }
  });

  $('#frmOrderServices').validate();

  $('#frmOrderUsage').validate();

  $('#frmOrderComment').validate({
    submitHandler: function(form) {
      var action = $(this).attr('action');
      $(form).ajaxSubmit({
        url: action,
        success: function(data) {
          window.location.reload();
        }
      });
    }
  });

  //Helpdesk - Log an Issue and View History
  // $('#form_user').validate({
  //   rules: {
  //       email: {
  //         required: true,
  //       }
  //   },
  // });

  $.validator.addMethod('filesize', function (value, element, param) {
  return this.optional(element) || (element.files[0].size <= param)
  }, 'File size must be less than {0}');
  
  $('#new-ticket-form').validate();
  $('#attachment-form').validate();

  function precisionRound(number, precision) {
    var factor = Math.pow(10, precision);
    return Math.round(number * factor) / factor;
  }

  function functionX(elem, error_class) {
    if(elem[0].files[0].size > (3*1054576)){
      $(error_class).html("This file is too large (" + precisionRound((elem[0].files[0].size)/1048576, 2) + " MB). <br>The maximum size allowed is 3 MB.");
      elem[0].value = "";
    }else if(elem[0].files[0].size < (1)){
      $(error_class).html("Please make sure the file has content.");
      elem[0].value = "";
    }else{
      $(error_class).contents().remove();
    };
  }

  $('#id_attachment').on('change', function () {
    var elem = $(this);
    functionX(elem, '.attachment_error');
  });

  $('#id_attachment2').on('change', function () {
    var elem = $(this);
    functionX(elem, '.attachment_error2');
  });

});

